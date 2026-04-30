import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from 'react';

interface ErrorBoundaryProps extends PropsWithChildren {
  fallbackTitle?: string;
  fallbackMessage?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('UI render boundary caught an error', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
          <p className="font-semibold text-white">{this.props.fallbackTitle ?? 'Section unavailable'}</p>
          <p className="mt-2 leading-6">
            {this.props.fallbackMessage ?? 'This section could not render. The rest of the workstation remains available.'}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-4 rounded-lg border border-rose-300/40 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-rose-50 transition hover:bg-rose-300/10"
          >
            Retry section
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
