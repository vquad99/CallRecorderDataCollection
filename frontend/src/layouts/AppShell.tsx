// Responsive application shell (FND-020): skip link, a white top bar across the page with the
// product, the phone line and the signed-in user, and under it a blue side menu grouped and
// filtered by permission (D-150); a two-panel layout for the signed-out pages. On narrow screens
// the side menu folds behind a menu button and opens over the page: Escape, a tap beside it or any
// of its links closes it. Until two-step sign-in is set up there is no menu at all (D-106). A
// moderator with a phone seat has their phone line kept Ready while signed in (D-133). Each page
// gets its own tab title (routes.tsx).
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { ROLE_LABELS } from "../api/admin";
import { useRouteTitle } from "../app/routeTitle";
import { useAuth } from "../auth/AuthContext";
import { IdleWarning } from "../auth/IdleWarning";
import { BrandMark, Icon, type IconName } from "../components/Icon";
import { PhoneLineProvider, PhoneLineStatus } from "../features/phoneline/PhoneLine";
import { PRODUCT } from "../hooks/usePageTitle";

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
      { to: "/payments", label: "Payments", permission: "payments.manage", icon: "money" },
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
  useRouteTitle();
  // The small-screen menu stays open only on the page where it was opened, so following a link
  // closes it.
  const [menuOpenOn, setMenuOpenOn] = useState<string | null>(null);
  const menuOpen = menuOpenOn === location.pathname;
  const menuButton = useRef<HTMLButtonElement>(null);
  // A sign-out whose request did not reach the server leaves the session live: say so, for as long
  // as that sign-in lasts (a later one starts without the message).
  const [signOutFailedFor, setSignOutFailedFor] = useState<object | null>(null);
  const signOutFailed = user !== null && signOutFailedFor === user;

  // Escape closes the open menu and puts the focus back on its button.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpenOn(null);
      menuButton.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

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
  // No menu until two-step sign-in is set up: nothing behind it would open (D-106).
  const bare = Boolean(user?.mfa_setup_required);
  const groups = GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => i.permission === null || can(i.permission)),
  })).filter((g) => g.items.length > 0);
  const closeMenu = () => setMenuOpenOn(null);
  const signOutNow = () => {
    setSignOutFailedFor(null);
    void signOut().then(
      () => navigate("/login"),
      () => setSignOutFailedFor(user),
    );
  };

  return (
    <PhoneLineProvider>
      <div className={bare ? "shell shell--bare" : "shell"}>
        {skip}
        <header className="topbar">
          {bare ? null : (
            <button
              ref={menuButton}
              type="button"
              className="topbar__menu"
              aria-expanded={menuOpen}
              aria-controls="side-nav"
              onClick={() => setMenuOpenOn(menuOpen ? null : location.pathname)}
            >
              <Icon name={menuOpen ? "close" : "menu"} />
              <span className="sr-only">Menu</span>
            </button>
          )}
          <Link to="/" className="topbar__brand">
            <Brand />
          </Link>
          <div className="topbar__spacer" />
          <PhoneLineStatus />
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
            <button type="button" className="topbar__signout" title="Sign out" onClick={signOutNow}>
              <Icon name="logout" size={16} />
              <span className="topbar__signout-words">Sign out</span>
            </button>
          </div>
        </header>
        {bare ? null : (
          <aside id="side-nav" className="sidenav" data-open={menuOpen || undefined}>
            <nav aria-label="Main" className="sidenav__nav">
              {groups.map((g) => (
                <div key={g.title} className="sidenav__group">
                  <p className="sidenav__title" aria-hidden="true">
                    {g.title}
                  </p>
                  {g.items.map((l) => (
                    <NavLink key={l.to} to={l.to} className="sidenav__link" onClick={closeMenu}>
                      {({ isActive }) => (
                        <>
                          <Icon
                            name={l.icon}
                            size={18}
                            tone="text"
                            weight={isActive ? "fill" : "regular"}
                          />
                          {l.label}
                        </>
                      )}
                    </NavLink>
                  ))}
                </div>
              ))}
            </nav>
            <p className="sidenav__foot" aria-hidden="true">
              <Icon name="lock" size={14} tone="text" weight="fill" /> Private workspace
            </p>
          </aside>
        )}
        {menuOpen && !bare ? (
          // A tap beside the open menu closes it instead of pressing the page under it.
          <button
            type="button"
            className="sidenav__backdrop"
            tabIndex={-1}
            aria-label="Close menu"
            onClick={closeMenu}
          />
        ) : null}
        <div className="shell__column">
          {signOutFailed ? (
            <p className="signout-failed" role="alert">
              <Icon name="warning" size={16} />
              <span>
                You are still signed in: the server could not be reached. Try Sign out again.
              </span>
            </p>
          ) : null}
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
          {user?.session_idle_minutes ? (
            <IdleWarning idleMinutes={user.session_idle_minutes} />
          ) : null}
          <main id="main" className="shell__main" tabIndex={-1}>
            <div className="shell__content">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </PhoneLineProvider>
  );
}
