import { Link } from 'react-router-dom';
import Footer from './Footer';

export default function NotFound() {
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

      <main className="flex flex-col items-center justify-center" style={{ flex: 1, textAlign: 'center', padding: 'var(--space-8) var(--space-4)' }}>
        <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: 'var(--space-3)' }}>404</h1>
        <p className="text-secondary" style={{ marginBottom: 'var(--space-5)', maxWidth: '400px' }}>
          This page doesn&apos;t exist. Maybe the drawing got deleted?
        </p>
        <Link to="/" className="btn btn--primary">
          Back to Home
        </Link>
      </main>

      <Footer />
    </div>
  );
}
