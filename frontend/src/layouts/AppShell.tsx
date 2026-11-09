// Responsive application shell (FND-020): skip link, header, navigation, main region.
import { NavLink, Outlet } from "react-router";

export function AppShell() {
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="shell__header">
        <span className="shell__brand">Conversation Collection</span>
        <nav aria-label="Main" className="shell__nav">
          <NavLink to="/" end className="shell__link">
            System status
          </NavLink>
        </nav>
      </header>
      <main id="main" className="shell__main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
