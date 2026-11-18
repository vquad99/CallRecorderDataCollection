#!/usr/bin/env bash
# The move from Render (D-132): copy every stored file (recordings, originals, exports, the app's
# dumps) from the Wasabi bucket into the new S3 bucket with the same keys, content types and SHA-256
# labels, then compare file counts and sizes. Run on the AWS server as the ccp user. Safe to run
# again: only new or changed files are copied. So run it a day before the move (the long part) and
# again in the move window (only what came since). docs/DEPLOYMENT_AWS.md 8.1 and 8.4:
#   read -rs SRC_ACCESS_KEY_ID; read -rs SRC_SECRET_ACCESS_KEY; export SRC_ACCESS_KEY_ID SRC_SECRET_ACCESS_KEY
#   deploy/aws/copy_files.sh                   copy, then compare counts and sizes
#   deploy/aws/copy_files.sh check             compare only (also checks MD5s where both sides have one)
#   deploy/aws/copy_files.sh check --download  compare every byte (downloads both sides; slow)
# The Wasabi keys are read from the environment, never stored. S3 is written with the server's role.
# Afterwards the app checks every file against its own SHA-256 label (verify-assets, 8.5).
set -euo pipefail

AWS_DIR="$(cd "$(dirname "$0")" && pwd)"
setting() { sed -n "s/^$1=//p" "$AWS_DIR/.env" | tail -n 1; }
RCLONE_IMAGE=rclone/rclone:1.75.2

SRC_ENDPOINT="${SRC_ENDPOINT:-https://s3.ap-southeast-1.wasabisys.com}"
SRC_REGION="${SRC_REGION:-ap-southeast-1}"
SRC_BUCKET="${SRC_BUCKET:-callrec57}"
PREFIX="${PREFIX:-$(setting STORAGE_KEY_PREFIX)}"
DST_BUCKET="${DST_BUCKET:-$(setting STORAGE_BUCKET)}"
DST_REGION="${DST_REGION:-$(setting STORAGE_REGION)}"
: "${SRC_ACCESS_KEY_ID:?set SRC_ACCESS_KEY_ID (Wasabi access key)}"
: "${SRC_SECRET_ACCESS_KEY:?set SRC_SECRET_ACCESS_KEY (Wasabi secret key)}"
[ -n "$DST_BUCKET" ] || { echo "copy: STORAGE_BUCKET is empty in deploy/aws/.env"; exit 1; }

# rclone settings by environment: "src" is Wasabi with its keys, "dst" is S3 with the server's role.
export RCLONE_CONFIG_SRC_TYPE=s3 RCLONE_CONFIG_SRC_PROVIDER=Wasabi
export RCLONE_CONFIG_SRC_ENDPOINT="$SRC_ENDPOINT" RCLONE_CONFIG_SRC_REGION="$SRC_REGION"
export RCLONE_CONFIG_SRC_ACCESS_KEY_ID="$SRC_ACCESS_KEY_ID"
export RCLONE_CONFIG_SRC_SECRET_ACCESS_KEY="$SRC_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_DST_TYPE=s3 RCLONE_CONFIG_DST_PROVIDER=AWS RCLONE_CONFIG_DST_ENV_AUTH=true
export RCLONE_CONFIG_DST_REGION="$DST_REGION" RCLONE_CONFIG_DST_NO_CHECK_BUCKET=true
export RCLONE_CONFIG_DST_ACL=bucket-owner-full-control
pass=()
for name in $(compgen -e | grep '^RCLONE_'); do pass+=(-e "$name"); done  # names only: no secret in argv
rclone() { docker run --rm "${pass[@]}" "$RCLONE_IMAGE" "$@"; }

SRC="src:$SRC_BUCKET/$PREFIX"
DST="dst:$DST_BUCKET/$PREFIX"

check() {
  local src dst
  src="$(rclone size --json "$SRC")"
  dst="$(rclone size --json "$DST")"
  echo "copy: Wasabi $src"
  echo "copy: S3     $dst"
  [ "$src" = "$dst" ] || { echo "copy: file counts or sizes DIFFER"; exit 1; }
  rclone check "$SRC" "$DST" --one-way "$@"
  echo "copy: counts, sizes and checks match"
}

if [ "${1:-}" = check ]; then shift; check "$@"; exit 0; fi
echo "copy: $SRC -> $DST"
# --metadata: keeps each file's content type and the app's sha256 label.
rclone copy "$SRC" "$DST" --metadata --transfers 16 --checkers 16 --stats 1m --stats-one-line -v
check
