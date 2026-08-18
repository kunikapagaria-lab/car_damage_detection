'use client';

import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-red-900 bg-red-950/30 p-8 text-center">
            <span className="text-2xl">⚠</span>
            <p className="text-sm text-red-400">
              {this.state.error?.message ?? 'An unexpected error occurred'}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="rounded-md bg-red-900 px-3 py-1 text-xs text-red-200 hover:bg-red-800"
            >
              Retry
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}

export function InlineError({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-red-900/60 bg-red-950/20 px-4 py-3 text-sm text-red-400">
      <span>⚠</span>
      <span className="flex-1">{message ?? 'Failed to load data'}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded px-2 py-0.5 text-xs bg-red-900/50 hover:bg-red-900"
        >
          Retry
        </button>
      )}
    </div>
  );
}
