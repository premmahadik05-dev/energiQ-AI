import { Component, type ErrorInfo, type ReactNode } from 'react';

interface State {
  error: Error | null;
}

/** Last line of defence: a rendering bug shows a message and a way out instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled UI error', error, info.componentStack);
  }

  override componentDidUpdate(prev: { resetKey?: string }): void {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto max-w-lg p-8">
        <h1 className="text-xl">Something went wrong on this page</h1>
        <p className="mt-2 text-ink-2">{this.state.error.message || 'An unexpected error occurred.'}</p>
        <div className="mt-4 flex gap-2">
          <button type="button" className="btn-primary" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
          <a href="/" className="btn-secondary">
            Go to the dashboard
          </a>
        </div>
      </div>
    );
  }
}
