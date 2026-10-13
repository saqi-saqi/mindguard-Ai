import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("MindGuard Uncaught React Error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-900 text-white flex items-center justify-center p-6 font-sans">
          <div className="max-w-md w-full rounded-2xl border border-rose-500/30 bg-slate-800 p-6 shadow-2xl text-center space-y-4">
            <div className="size-12 mx-auto rounded-xl bg-rose-500/20 text-rose-400 grid place-items-center text-xl font-bold">
              ⚠️
            </div>
            <h1 className="text-lg font-bold text-white font-heading">Something went wrong</h1>
            <p className="text-xs text-slate-300 leading-relaxed">
              An unexpected error occurred while rendering this view.
            </p>
            {this.state.error?.message && (
              <pre className="text-[11px] text-rose-300 bg-slate-950 p-3 rounded-xl overflow-x-auto text-left font-mono">
                {this.state.error.message}
              </pre>
            )}
            <div className="flex gap-2 justify-center pt-2">
              <button
                type="button"
                onClick={this.handleReset}
                className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-500 cursor-pointer shadow-xs"
              >
                Reload MindGuard
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
