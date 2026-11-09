// Responsive application shell (FND-020): skip link, header, navigation filtered by permission.
import { NavLink, Outlet, useNavigate } from "react-router";

import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/form/Button";

const LINKS = [
  { to: "/projects", label: "Projects", permission: "projects.view" },
  { to: "/admin/users", label: "Users", permission: "users.manage" },
  { to: "/admin/settings", label: "Settings", permission: "settings.manage" },
  { to: "/status", label: "System status", permission: null },
];

export function AppShell() {
  const { status, user, can, signOut } = useAuth();
  const navigate = useNavigate();
  const signedIn = status === "authenticated";

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="shell__header">
        <span className="shell__brand">Conversation Collection</span>
        {signedIn ? (
          <>
            <nav aria-label="Main" className="shell__nav">
              {LINKS.filter((l) => l.permission === null || can(l.permission)).map((l) => (
                <NavLink key={l.to} to={l.to} className="shell__link">
                  {l.label}
                </NavLink>
              ))}
            </nav>
            <div className="shell__user">
              <NavLink to="/account" className="shell__link">
                {user?.display_name}
              </NavLink>
              <Button
                variant="secondary"
                onClick={() => void signOut().then(() => navigate("/login"))}
              >
                Sign out
              </Button>
            </div>
          </>
        ) : null}
      </header>
      <main id="main" className="shell__main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
