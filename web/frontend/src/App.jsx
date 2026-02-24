import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { auth, signInAnonymously } from './lib/firebase';
import Workspace from './components/Workspace';
import Privacy from './components/Privacy';
import Terms from './components/Terms';
import NotFound from './components/NotFound';

function AutoAuth({ user, loading, children, onSignOut }) {
  useEffect(() => {
    if (!loading && !user) {
      signInAnonymously(auth).catch(() => {});
    }
  }, [user, loading]);

  if (loading || !user) {
    return (
      <div className="flex items-center justify-center" style={{ height: '100vh' }}>
        <div className="spinner spinner--lg" role="status">
          <span className="sr-only">Loading...</span>
        </div>
      </div>
    );
  }

  return <Workspace user={user} onSignOut={onSignOut} />;
}

export default function App() {
  const authState = useAuth();
  const { user, loading } = authState;

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={<AutoAuth user={user} loading={loading} onSignOut={authState.signOut} />}
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
