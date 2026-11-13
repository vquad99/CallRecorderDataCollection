// Responsive application shell (FND-020): skip link, dark side navigation grouped and filtered by
// permission, a top bar with the page context and the signed-in user, and a two-panel layout for
// the signed-out pages. On narrow screens the side navigation folds behind a menu button.
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { ROLE_LABELS } from "../api/admin";
import { useAuth } from "../auth/AuthContext";
import { BrandMark, Icon, type IconName } from "../components/Icon";

import { LoginArt } from "../components/Art";

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
      { to: "/calls", label: "Phone calls", permission: "calls.end", icon: "phone" },
      {
        to: "/participants",
        label: "Participants",
        permission: "participants.manage",
        icon: "people",
      },
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
    items: [
      { to: "/status", label: "System status", permission: "settings.manage", icon: "status" },
    ],
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
  const { status, user, can, signOut, stopViewing } = useAuth();
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
    // rebuilt when the check finishes; only the brand panel waits.
    return (
      <div className={status === "loading" ? "public public--checking" : "public"}>
        {skip}
        <div className="public__panel" aria-hidden="true">
          <div className="public__top">
            <Brand />
            <span className="public__fig">
              <span>Fig. 01</span> / Speech data
            </span>
          </div>
          <div className="public__stats">
            <div>
              <strong>2 speakers</strong>per conversation
            </div>
            <div>
              <strong>16 kHz</strong>delivery audio
            </div>
            <div>
              <strong>Lossless</strong>capture
            </div>
            <div>
              <strong>Consent</strong>on record
            </div>
          </div>
          <div className="public__stage">
            <div className="public__art">{status === "loading" ? null : <LoginArt />}</div>
            <p className="public__headline">Collect real conversations, with consent.</p>
          </div>
          <div className="public__bottom">
            <span>Private workspace</span>
            <span>Every action audited</span>
          </div>
        </div>
        <main id="main" className="public__main" tabIndex={-1}>
          <div className="public__content">
            <div className="public__brand">
              <Brand />
            </div>
            <Outlet />
            <p className="public__foot">Authorised staff only. Every action is recorded.</p>
          </div>
        </main>
      </div>
    );
  }

  const roles = (user?.roles ?? []).map((r) => ROLE_LABELS[r] ?? r).join(", ");
  const groups = GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => i.permission === null || can(i.permission)),
  })).filter((g) => g.items.length > 0);
  const current = groups
    .flatMap((g) => g.items.map((i) => ({ ...i, group: g.title })))
    .find((i) => location.pathname === i.to || location.pathname.startsWith(`${i.to}/`));

  return (
    <div className="shell">
      {skip}
      <aside id="side-nav" className="sidenav" data-open={menuOpen || undefined}>
        <div className="sidenav__brand">
          <Brand />
        </div>
        <nav aria-label="Main" className="sidenav__nav">
          {groups.map((g) => (
            <div key={g.title} className="sidenav__group">
              <p className="sidenav__title" aria-hidden="true">
                {g.title}
              </p>
              {g.items.map((l) => (
                <NavLink key={l.to} to={l.to} className="sidenav__link">
                  {({ isActive }) => (
                    <>
                      <Icon name={l.icon} size={18} weight={isActive ? "fill" : "regular"} />
                      {l.label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <p className="sidenav__foot" aria-hidden="true">
          <Icon name="lock" size={14} /> Private workspace
        </p>
      </aside>
      <div className="shell__column">
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
          {/* Page context, drawn by the stylesheet so it adds no duplicate text to the page. */}
          <div
            className="crumbs"
            aria-hidden="true"
            data-section={current?.group ?? "Account"}
            data-page={current?.label ?? "My account"}
          />
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
        {user?.viewer ? (
          <div className="view-as" role="status">
            <Icon name="info" size={16} />
            <span>
              Viewing as <strong>{user.display_name}</strong> ({roles}). Read-only: nothing can be
              changed.
            </span>
            <button
              type="button"
              className="view-as__stop"
              onClick={() => void stopViewing().then(() => navigate("/admin/users"))}
            >
              Stop viewing
            </button>
          </div>
        ) : null}
        <main id="main" className="shell__main" tabIndex={-1}>
          <div className="shell__content">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
