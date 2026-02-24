import { useState } from 'react';
import { Link } from 'react-router-dom';
import Footer from './Footer';

export default function Login({ auth }) {
  const { error, clearError, signInWithGoogle, signInWithEmail, signUpWithEmail } = auth;
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    if (mode === 'signup') {
      await signUpWithEmail(email, password);
    } else {
      await signInWithEmail(email, password);
    }
    setSubmitting(false);
  };

  const handleGoogleSignIn = async () => {
    setSubmitting(true);
    await signInWithGoogle();
    setSubmitting(false);
  };

  return (
    <div className="page">
      <header className="site-header">
        <div className="container site-header__inner">
          <Link to="/" className="site-header__logo">
            <div className="site-header__logo-icon" aria-hidden="true">C</div>
            CAD DXF Agent
          </Link>
        </div>
      </header>

      <main className="flex items-center justify-center" style={{ flex: 1, padding: 'var(--space-6) 0' }}>
        <div className="container container--narrow">
          <div className="card" style={{ maxWidth: '420px', margin: '0 auto' }}>
            <h2 style={{ textAlign: 'center', marginBottom: 'var(--space-5)' }}>
              {mode === 'signup' ? 'Create an account' : 'Welcome back'}
            </h2>

            <button
              type="button"
              className="btn btn--secondary btn--full"
              onClick={handleGoogleSignIn}
              disabled={submitting}
              aria-label="Sign in with Google"
            >
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
                <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"/>
                <path fill="#FBBC05" d="M3.964 10.706A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.706V4.962H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.038l3.007-2.332z"/>
                <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.962L3.964 7.294C4.672 5.163 6.656 3.58 9 3.58z"/>
              </svg>
              Continue with Google
            </button>

            <div className="divider">or</div>

            <form onSubmit={handleSubmit}>
              <div className="flex flex-col gap-3">
                <div className="input-group">
                  <label className="input-group__label" htmlFor="email">Email</label>
                  <input
                    id="email"
                    type="email"
                    className="input-group__field"
                    value={email}
                    onChange={(e) => { setEmail(e.target.value); clearError(); }}
                    placeholder="you@example.com"
                    required
                    autoComplete="email"
                  />
                </div>
                <div className="input-group">
                  <label className="input-group__label" htmlFor="password">Password</label>
                  <input
                    id="password"
                    type="password"
                    className="input-group__field"
                    value={password}
                    onChange={(e) => { setPassword(e.target.value); clearError(); }}
                    placeholder="At least 6 characters"
                    required
                    minLength={6}
                    autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                  />
                </div>

                {error && (
                  <p className="input-group__error" role="alert">{error}</p>
                )}

                <button
                  type="submit"
                  className="btn btn--primary btn--full"
                  disabled={submitting}
                >
                  {submitting ? (
                    <span className="spinner" aria-hidden="true" />
                  ) : mode === 'signup' ? 'Create Account' : 'Sign In'}
                </button>
              </div>
            </form>

            <p className="text-center text-sm mt-4" style={{ color: 'var(--text-secondary)' }}>
              {mode === 'signup' ? (
                <>
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => { setMode('signin'); clearError(); }}
                    style={{ color: 'var(--accent-primary)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 500 }}
                  >
                    Sign in
                  </button>
                </>
              ) : (
                <>
                  Don&apos;t have an account?{' '}
                  <button
                    type="button"
                    onClick={() => { setMode('signup'); clearError(); }}
                    style={{ color: 'var(--accent-primary)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 500 }}
                  >
                    Create one
                  </button>
                </>
              )}
            </p>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
