import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import Landing from './components/Landing';
import Login from './components/Login';
import Workspace from './components/Workspace';
import Privacy from './components/Privacy';
import Terms from './components/Terms';
import NotFound from './components/NotFound';

function ProtectedRoute({ user, children }) {
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const authState = useAuth();
  const { user, loading } = authState;

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height: '100vh' }}>
        <div className="spinner spinner--lg" role="status">
          <span className="sr-only">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={user ? <Navigate to="/app" replace /> : <Landing />} />
        <Route path="/login" element={user ? <Navigate to="/app" replace /> : <Login auth={authState} />} />
        <Route
          path="/app"
          element={
            <ProtectedRoute user={user}>
              <Workspace user={user} onSignOut={authState.signOut} />
            </ProtectedRoute>
          }
        />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
