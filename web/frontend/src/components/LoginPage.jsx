import { Link } from 'react-router-dom';

export default function LoginPage({ onSignInWithGoogle, error, clearError }) {
  return (
    <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div className="card" style={{ maxWidth: 420, width: '100%', textAlign: 'center' }}>
        <div className="site-header__logo-icon" aria-hidden="true"
             style={{ width: 64, height: 64, fontSize: 28, margin: '0 auto var(--space-4)' }}>
          I
        </div>
        <h1 className="font-display" style={{ fontSize: '1.75rem', marginBottom: 'var(--space-1)' }}>IntentCAD</h1>
        <p className="text-muted" style={{ marginBottom: 'var(--space-5)', fontSize: '1.05rem' }}>
          CAD with Intent
        </p>

        <ul style={{
          textAlign: 'left',
          listStyle: 'none',
          padding: 0,
          margin: '0 0 var(--space-6)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
        }}>
          <li className="text-sm text-secondary" style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)' }}>
            <span style={{ color: 'var(--accent-primary)', flexShrink: 0 }}>&mdash;</span>
            Edit drawings with natural language
          </li>
          <li className="text-sm text-secondary" style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)' }}>
            <span style={{ color: 'var(--accent-primary)', flexShrink: 0 }}>&mdash;</span>
            Compare revisions side-by-side
          </li>
          <li className="text-sm text-secondary" style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)' }}>
            <span style={{ color: 'var(--accent-primary)', flexShrink: 0 }}>&mdash;</span>
            DXF, DWG, PDF support
          </li>
        </ul>

        {error && (
          <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)', textAlign: 'left' }}>
            <span>{error}</span>
            <button className="btn btn--ghost btn--sm" onClick={clearError}
                    style={{ marginLeft: 'auto' }}>&times;</button>
          </div>
        )}

        <button className="btn btn--primary btn--lg" onClick={onSignInWithGoogle}
                style={{ width: '100%', gap: 'var(--space-2)' }}>
          <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#4285F4" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#34A853" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59a14.5 14.5 0 010-9.18l-7.98-6.19a24.02 24.02 0 000 21.56l7.98-6.19z"/>
            <path fill="#EA4335" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          Sign in with Google
        </button>

        <p className="text-muted" style={{ marginTop: 'var(--space-6)', fontSize: '0.8rem' }}>
          by Intent Solutions
        </p>
        <p className="text-muted" style={{ marginTop: 'var(--space-2)', fontSize: '0.75rem' }}>
          <Link to="/privacy">Privacy</Link> &middot; <Link to="/terms">Terms</Link>
        </p>
      </div>
    </div>
  );
}
