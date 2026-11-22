#!/usr/bin/env bash
# Build and start Conversation Collection on the AWS server (D-132). As the ccp user:
#   deploy/aws/deploy.sh                  deploy origin/main now (also: apply a changed .env)
#   NO_PULL=1 deploy/aws/deploy.sh        deploy the code as it is on disk (CI's aws-stack job)
#   deploy/aws/deploy.sh --if-changed     the timer, every minute: deploy only when origin/main moved
#   deploy/aws/deploy.sh rollback [TAG]   start an earlier deploy's images again (default: the previous)
#   deploy/aws/deploy.sh status           what runs now, and which images are kept
#
# A deploy: build images tagged with the commit while the old containers keep serving; run the
# database migrations (Render's pre-deploy step); swap the containers (the API is away for a few
# seconds); if they do not become healthy, start the previous images again. The newest KEEP_IMAGES
# builds stay on the server for rollback. A commit that changes no image (docs only) restarts
# nothing. The timer stays idle until the first deploy by hand has worked. Summary lines also go to
# OPS_LOG (the timer sets /var/log/ccp/operations.log; CloudWatch alarms on "FAILED").
set -euo pipefail

AWS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$AWS_DIR/../.." && pwd)"
STATE="$AWS_DIR/.state"
BRANCH="${DEPLOY_BRANCH:-main}"
KEEP_IMAGES="${KEEP_IMAGES:-3}"
WAIT=(--wait --wait-timeout 300)

say() {
  echo "deploy: $*"
  if [ -n "${OPS_LOG:-}" ]; then echo "$(date -u +%FT%TZ) deploy: $*" >> "$OPS_LOG" || true; fi
}
fail() { say "FAILED: $*"; exit 1; }
image_id() { docker image inspect --format '{{.Id}}' "$1" 2>/dev/null || true; }
state() { cat "$STATE/$1" 2>/dev/null || true; }
compose() { bash "$AWS_DIR/compose.sh" "$@"; }

# One deploy (or database copy or restore) at a time. The timer gives up at once; by hand, wait.
lock() {
  [ -z "${CCP_DEPLOY_LOCKED:-}" ] || return 0
  exec 9>"$STATE/deploy.lock"
  if [ "$1" = nowait ]; then
    flock -n 9 || exit 0
  else
    flock -w 3600 9 || fail "another deploy, copy or restore holds the lock"
  fi
  export CCP_DEPLOY_LOCKED=1
}

checks() {
  test -f "$AWS_DIR/.env" || fail "deploy/aws/.env is missing (copy env.example)"
  if ! grep -q '^DB_HOST=.' "$AWS_DIR/.env" && [ "${CI:-}" != true ] && [ "${LOCAL_DB:-}" != 1 ]; then
    fail "DB_HOST is empty in deploy/aws/.env; the stand-in database is for CI and trials (LOCAL_DB=1)"
  fi
}

pull() {
  git -C "$REPO" fetch --quiet origin "$BRANCH" || fail "git fetch from origin"
  git -C "$REPO" merge --ff-only --quiet "origin/$BRANCH" \
    || fail "the checkout cannot move to origin/$BRANCH (local changes or rewritten history)"
}

prune() {
  local repo tag keep
  keep=" $(state live) $(state previous) "
  for repo in ccp-backend ccp-web; do
    docker image ls "$repo" --format '{{.Tag}}' | tail -n +"$((KEEP_IMAGES + 1))" | while read -r tag; do
      case "$keep" in *" $tag "*) continue ;; esac
      docker image rm "$repo:$tag" >/dev/null 2>&1 || true
    done
  done
  docker image prune -f >/dev/null 2>&1 || true
  docker builder prune -f --filter until=168h >/dev/null 2>&1 || true
}

deploy_here() {
  local sha tag live
  sha="$(git -C "$REPO" rev-parse HEAD)"
  tag="${sha:0:12}"
  live="$(state live)"
  echo "$sha" > "$STATE/attempted"

  say "building $tag"
  IMAGE_TAG="$tag" compose build api web || fail "build of $tag (the running version is untouched)"

  if [ -n "$live" ] && [ "$tag" != "$live" ] \
    && [ "$(image_id "ccp-backend:$tag")" = "$(image_id "ccp-backend:$live")" ] \
    && [ "$(image_id "ccp-web:$tag")" = "$(image_id "ccp-web:$live")" ]; then
    docker image rm "ccp-backend:$tag" "ccp-web:$tag" >/dev/null
    IMAGE_TAG="$live" compose up -d "${WAIT[@]}" --no-build --remove-orphans || fail "settings change on $live"
    say "$tag changes no image; $live keeps running"
    return 0
  fi

  say "migrating the database for $tag"
  IMAGE_TAG="$tag" compose run --rm -T migrate || fail "migrations of $tag (the old version keeps running)"

  say "starting $tag"
  if ! IMAGE_TAG="$tag" compose up -d "${WAIT[@]}" --no-build --remove-orphans; then
    IMAGE_TAG="$tag" compose logs --no-color --tail 40 api worker exports-worker web || true
    if [ -n "$live" ] && [ "$live" != "$tag" ]; then
      IMAGE_TAG="$live" compose up -d "${WAIT[@]}" --no-build || true
      say "started $live again"
    fi
    fail "$tag did not become healthy"
  fi
  if [ -n "$live" ] && [ "$live" != "$tag" ]; then echo "$live" > "$STATE/previous"; fi
  echo "$tag" > "$STATE/live"
  prune
  say "$tag is live ($(git -C "$REPO" log -1 --format=%s | cut -c1-80))"
}

rollback() {
  local target="${1:-$(state previous)}" live
  live="$(state live)"
  [ -n "$target" ] || fail "rollback: no previous deploy; '$0 status' lists the kept images"
  [ -n "$(image_id "ccp-backend:$target")" ] && [ -n "$(image_id "ccp-web:$target")" ] \
    || fail "rollback: the images of $target are not on this server ('$0 status')"
  say "rolling back from ${live:-nothing} to $target (database migrations are not undone)"
  IMAGE_TAG="$target" compose up -d "${WAIT[@]}" --no-build || fail "rollback to $target"
  if [ -n "$live" ] && [ "$live" != "$target" ]; then echo "$live" > "$STATE/previous"; fi
  echo "$target" > "$STATE/live"
  say "$target is live; the timer deploys again at the next push to $BRANCH"
}

status() {
  echo "checkout:  $(git -C "$REPO" log -1 --format='%h %cd %s' --date=short)"
  echo "live:      $(state live)"
  echo "previous:  $(state previous)"
  echo "attempted: $(state attempted | cut -c1-12)"
  echo "kept images (newest first):"
  docker image ls ccp-backend --format '  {{.Tag}}  {{.CreatedSince}}'
  compose ps
}

main() {
  mkdir -p "$STATE"
  case "${1:-}" in
    --if-changed)
      [ -f "$AWS_DIR/.env" ] && [ -f "$STATE/live" ] || exit 0
      lock nowait
      local remote
      remote="$(git -C "$REPO" ls-remote origin "refs/heads/$BRANCH" 2>/dev/null | cut -f1)" || true
      if [ -z "$remote" ]; then
        [ -f "$STATE/origin-unreachable" ] || say "cannot reach origin (GitHub); trying every minute"
        touch "$STATE/origin-unreachable"
        exit 0
      fi
      rm -f "$STATE/origin-unreachable"
      [ "$remote" != "$(state attempted)" ] || exit 0
      say "origin/$BRANCH is now ${remote:0:12}"
      echo "$remote" > "$STATE/attempted"  # tried once per push; a failure waits for the next push
      checks
      pull
      exec bash "$AWS_DIR/deploy.sh" --here  # the script just pulled does the deploy
      ;;
    --here) lock wait; checks; deploy_here ;;
    "")
      lock wait
      checks
      [ -n "${NO_PULL:-}" ] || pull
      exec bash "$AWS_DIR/deploy.sh" --here
      ;;
    rollback) lock wait; checks; rollback "${2:-}" ;;
    status) status ;;
    *) sed -n '2,7p' "$0"; exit 2 ;;
  esac
}

main "$@"
