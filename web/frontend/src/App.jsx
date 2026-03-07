import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import Workspace from './components/Workspace';
import LoginPage from './components/LoginPage';
import Privacy from './components/Privacy';
import Terms from './components/Terms';
import NotFound from './components/NotFound';

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
  );
}
