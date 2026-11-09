// Global error boundary (FND-017): a render error shows a recoverable message, not a blank page.
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
        <ErrorState
          message="The page failed to display. Reload to try again."
          onRetry={() => window.location.reload()}
        />
      );
    }
    return this.props.children;
  }
}
