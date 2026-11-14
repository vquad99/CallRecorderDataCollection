// The one page open to an admin who has not set up two-step sign-in yet (D-106). The server
// refuses everything else for such an account; this page says why and does the set-up.
import { Link, useNavigate } from "react-router";

import { ROLE_LABELS } from "../api/admin";
import { IconTile } from "../components/Icon";
import { useAuth } from "./AuthContext";
import { TwoStepEnrol } from "./TwoStepEnrol";

export function TwoStepSetupPage() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  // Already set up, or never needed: say so, instead of a form that would do nothing.
  if (user && !user.mfa_setup_required) {
    return (
      <section aria-labelledby="two-step-title" className="stack twostep">
        <h1 id="two-step-title">
          <IconTile name="lock" tone="blue" />
          Two-step sign-in
        </h1>
        <p>
          Nothing to set up here: two-step sign-in is{" "}
          {user.mfa_enabled ? "on for your account" : "not required for your role"}. You can turn it
          on or off on <Link to="/account">your account page</Link>.
        </p>
      </section>
    );
  }
  const roles = (user?.roles ?? []).map((r) => ROLE_LABELS[r] ?? r).join(", ");
  return (
    <section aria-labelledby="two-step-title" className="stack twostep">
      <h1 id="two-step-title">
        <IconTile name="lock" tone="blue" />
        Set up two-step sign-in
      </h1>
      <p>
        Your role ({roles}) needs two-step sign-in. From now on you sign in with your password and a
        6-digit code from an authenticator app on your phone. The rest of the application opens as
        soon as this is done.
      </p>
      <div className="card">
        <TwoStepEnrol
          onDone={async () => {
            await refresh();
            void navigate("/", { replace: true });
          }}
        />
      </div>
      <p className="muted">
        Keep the phone with the authenticator app. If you lose it, a Super Admin can reset your
        two-step sign-in from your user page, and you set it up again here.
      </p>
    </section>
  );
}
