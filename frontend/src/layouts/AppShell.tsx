// Responsive application shell (FND-020): skip link, top bar, grouped side navigation filtered by
// permission, and a plain centred layout for the signed-out pages. On narrow screens the side
// navigation folds behind a menu button in the top bar.
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { ROLE_LABELS } from "../api/admin";
import { useAuth } from "../auth/AuthContext";
import { BrandMark, Icon, type IconName } from "../components/Icon";

interface NavItem {
  to: string;
  label: string;
  permission: string | null;
  icon: IconName;
}

const GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Workspace",
    items: [
      { to: "/dashboard", label: "Dashboard", permission: "dashboard.view", icon: "chart" },
      { to: "/projects", label: "Projects", permission: "projects.view", icon: "projects" },
      { to: "/tasks", label: "Tasks", permission: "tasks.view", icon: "tasks" },
    ],
  },
  {
    title: "Administration",
    items: [
      { to: "/admin/users", label: "Users", permission: "users.manage", icon: "users" },
      { to: "/admin/settings", label: "Settings", permission: "settings.manage", icon: "settings" },
      { to: "/admin/audit", label: "Audit log", permission: "audit.view", icon: "audit" },
    ],
  },
  {
    title: "System",
    items: [{ to: "/status", label: "System status", permission: null, icon: "status" }],
  },
];

const PRODUCT = "Conversation Collection";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

function Brand() {
  return (
    <span className="brand">
      <BrandMark />
      <span className="brand__name">{PRODUCT}</span>
    </span>
  );
}

export function AppShell() {
  const { status, user, can, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // The small-screen menu stays open only on the page where it was opened, so following a link
  // closes it.
  const [menuOpenOn, setMenuOpenOn] = useState<string | null>(null);
  const menuOpen = menuOpenOn === location.pathname;

  const skip = (
    <a className="skip-link" href="#main">
      Skip to content
    </a>
  );

  if (status !== "authenticated") {
    // One tree while the sign-in check runs and after it, so a page being typed into is not
    // rebuilt when the check finishes.
    return (
      <div className="public">
        {skip}
        <main id="main" className="public__main" tabIndex={-1}>
          <div className="public__brand">
            <Brand />
          </div>
          <div
            className={status === "loading" ? "public__card public__card--plain" : "public__card"}
          >
            <Outlet />
          </div>
          <p className="public__foot">Authorised staff only. Every action is recorded.</p>
        </main>
      </div>
    );
  }

  const roles = (user?.roles ?? []).map((r) => ROLE_LABELS[r] ?? r).join(", ");
  const groups = GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => i.permission === null || can(i.permission)),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="shell">
      {skip}
      <header className="topbar">
        <button
          type="button"
          className="topbar__menu"
          aria-expanded={menuOpen}
          aria-controls="side-nav"
          onClick={() => setMenuOpenOn(menuOpen ? null : location.pathname)}
        >
          <Icon name={menuOpen ? "close" : "menu"} />
          <span className="sr-only">Menu</span>
        </button>
        <Brand />
        <div className="topbar__spacer" />
        <div className="topbar__user">
          <NavLink to="/account" className="topbar__account">
            <span className="avatar" aria-hidden="true">
              {initials(user?.display_name ?? "")}
            </span>
            <span className="topbar__who">
              <span className="topbar__name">{user?.display_name}</span>
              <span className="topbar__role" aria-hidden="true">
                {roles}
              </span>
            </span>
          </NavLink>
          <button
            type="button"
            className="topbar__signout"
            onClick={() => void signOut().then(() => navigate("/login"))}
          >
            <Icon name="logout" size={16} />
            Sign out
          </button>
        </div>
      </header>
      <div className="shell__body">
        <aside id="side-nav" className="sidenav" data-open={menuOpen || undefined}>
          <nav aria-label="Main">
            {groups.map((g) => (
              <div key={g.title} className="sidenav__group">
                <p className="sidenav__title" aria-hidden="true">
                  {g.title}
                </p>
                {g.items.map((l) => (
                  <NavLink key={l.to} to={l.to} className="sidenav__link">
                    <Icon name={l.icon} size={18} />
                    {l.label}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
        </aside>
        <main id="main" className="shell__main" tabIndex={-1}>
          <div className="shell__content">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
