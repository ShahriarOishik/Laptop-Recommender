import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

interface Props {
  children: ReactNode;
  /** Optional label for what crashed, shown in the fallback ("the chat",
   * "the comparison view"). Falls back to a generic message without it. */
  section?: string;
}

interface State {
  error: Error | null;
}

/** Catches render/lifecycle exceptions anywhere below it so one broken
 * component shows a recoverable message instead of a blank white screen.
 * Class component because error boundaries have no hook equivalent. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", this.props.section ?? "app", error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex h-full min-h-[240px] w-full flex-col items-center justify-center gap-3 p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-[var(--color-danger)]" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold text-[var(--color-text)]">
            {this.props.section ? `Something went wrong in ${this.props.section}.` : "Something went wrong."}
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            The rest of the app should still work — try again, or reload the page.
          </p>
        </div>
        <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={this.reset}>
          Try again
        </Button>
      </div>
    );
  }
}
