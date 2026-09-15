import React from "react";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Never log the error verbatim — could contain user data. Keep it thin.
    if (typeof console !== "undefined") {
      console.error("KIRA UI error:", error.name, info.componentStack?.split("\n")[0]);
    }
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="p-4 m-4 rounded-xl border border-red-500/60 bg-red-500/10">
          <div className="text-sm font-medium text-red-300">
            Something went wrong in this pane.
          </div>
          <div className="text-xs text-kira-muted mt-1">
            {this.state.error.name}: {this.state.error.message.slice(0, 200)}
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-3 px-3 py-1 rounded border border-kira-border hover:border-kira-accent text-sm"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
