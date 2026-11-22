// Global error boundary (FND-017): a render error outside the pages (the router's own RouteError
// handles theirs) shows the same recoverable message, not a blank page, and never the error itself.
import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "./StateViews";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  override render() {
    if (this.state.error) {
      return (
        <main id="main" className="route-error">
          <ErrorState
            title="This page could not be shown"
            message="Reload the page to try again. If it keeps happening, tell your administrator."
            onRetry={() => window.location.reload()}
          />
        </main>
      );
    }
    return this.props.children;
  }
}
