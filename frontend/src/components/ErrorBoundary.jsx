import React from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default class ErrorBoundary extends React.Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Unhandled UI error:", error, info);
  }

  handleReload = () => {
    window.location.href = "/dashboard";
  };

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center px-6" data-testid="error-boundary">
          <div className="max-w-md text-center">
            <div className="w-14 h-14 rounded-2xl bg-destructive/10 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-7 h-7 text-destructive" />
            </div>
            <h1 className="font-heading text-xl font-semibold">Something went wrong</h1>
            <p className="text-muted-foreground mt-2">This page hit an unexpected error. Your data is safe — try reloading.</p>
            <Button onClick={this.handleReload} className="rounded-full mt-6" data-testid="error-boundary-reload">
              Back to dashboard
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
