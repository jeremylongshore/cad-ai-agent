import { Component } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import Workspace from './components/Workspace';
import LoginPage from './components/LoginPage';
import Privacy from './components/Privacy';
import Terms from './components/Terms';
import NotFound from './components/NotFound';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[IntentCAD] Unhandled error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100vh', gap: '16px',
          fontFamily: 'system-ui, sans-serif', color: '#ccc', background: '#1a1a2e',
        }}>
          <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Something went wrong</h1>
          <p style={{ color: '#888', maxWidth: 400, textAlign: 'center' }}>
            An unexpected error occurred. Please reload the page to continue.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 24px', border: '1px solid #444', borderRadius: '6px',
              background: 'transparent', color: '#ccc', cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function AuthGate({ user, loading, authState }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height: '100vh' }}>
        <div className="spinner spinner--lg" role="status">
          <span className="sr-only">Loading...</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <LoginPage
        onSignInWithGoogle={authState.signInWithGoogle}
        onSignInWithEmail={authState.signInWithEmail}
        error={authState.error}
        clearError={authState.clearError}
      />
    );
  }

  return <Workspace user={user} onSignOut={authState.signOut} />;
}

export default function App() {
  const authState = useAuth();
  const { user, loading } = authState;

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route
            path="/"
            element={<AuthGate user={user} loading={loading} authState={authState} />}
          />
          <Route path="/app" element={<Navigate to="/" replace />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
