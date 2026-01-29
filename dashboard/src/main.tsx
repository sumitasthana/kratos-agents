import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null; info: React.ErrorInfo | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null, info: null };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    this.setState({ error, info });
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ fontFamily: "Segoe UI, Arial, sans-serif", padding: 16 }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: "#b00020" }}>
            Dashboard crashed
          </div>
          <div style={{ marginTop: 8, color: "#333" }}>{this.state.error.message}</div>
          <pre
            style={{
              marginTop: 12,
              background: "#0b1020",
              color: "#e6edf3",
              padding: 12,
              borderRadius: 8,
              overflow: "auto",
              fontSize: 12,
            }}
          >
            {this.state.error.stack}
          </pre>
          {this.state.info?.componentStack ? (
            <pre
              style={{
                marginTop: 12,
                background: "#0b1020",
                color: "#e6edf3",
                padding: 12,
                borderRadius: 8,
                overflow: "auto",
                fontSize: 12,
              }}
            >
              {this.state.info.componentStack}
            </pre>
          ) : null}
        </div>
      );
    }

    return this.props.children;
  }
}

window.addEventListener("error", (e) => {
  // Ensure there is always something visible in catastrophic failures
  // (React errors should be caught by ErrorBoundary, this is a fallback)
  console.error("[dashboard] window.error", e.error || e.message);
});

window.addEventListener("unhandledrejection", (e) => {
  console.error("[dashboard] unhandledrejection", e.reason);
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
