import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { auth, signInAnonymously } from '../lib/firebase';
import Footer from './Footer';

export default function Landing() {
  const navigate = useNavigate();
  const [trying, setTrying] = useState(false);

  const handleTryNow = async () => {
    setTrying(true);
    try {
      await signInAnonymously(auth);
      navigate('/app');
    } catch {
      navigate('/login');
    } finally {
      setTrying(false);
    }
  };

  return (
    <div className="page">
      <header className="site-header">
        <div className="container site-header__inner">
          <div className="site-header__logo">
            <div className="site-header__logo-icon" aria-hidden="true">C</div>
            CAD DXF Agent
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              className="btn btn--primary"
              onClick={handleTryNow}
              disabled={trying}
            >
              Try Free
            </button>
            <Link to="/login" className="btn btn--secondary">Sign In</Link>
          </div>
        </div>
      </header>

      <main>
        <section style={{ padding: 'var(--space-8) 0' }}>
          <div className="container" style={{ textAlign: 'center', maxWidth: '720px' }}>
            <h1 style={{ marginBottom: 'var(--space-4)' }}>
              Edit CAD drawings with AI
            </h1>
            <p style={{ fontSize: 'var(--text-xl)', color: 'var(--text-secondary)', marginBottom: 'var(--space-6)' }}>
              Upload your file. Describe the change. Review and download.
            </p>
            <div className="flex gap-4 justify-center" style={{ flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn btn--primary btn--lg"
                onClick={handleTryNow}
                disabled={trying}
              >
                {trying ? 'Loading...' : 'Try It Now — No Account Needed'}
              </button>
              <Link to="/login" className="btn btn--secondary btn--lg">
                Sign In
              </Link>
            </div>
          </div>
        </section>

        <section style={{ padding: 'var(--space-7) 0', background: 'var(--bg-secondary)' }}>
          <div className="container">
            <h2 style={{ textAlign: 'center', marginBottom: 'var(--space-6)' }}>
              What you can do
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--space-5)' }}>
              <article className="card">
                <div className="card__icon" aria-hidden="true">&#8596;</div>
                <h3 className="card__title">Move entities</h3>
                <p className="card__text">
                  "Move the east wall 12 inches north" &mdash; relocate lines, blocks, and groups
                  with plain-language directions. No coordinate math needed.
                </p>
              </article>
              <article className="card">
                <div className="card__icon" aria-hidden="true">&#9998;</div>
                <h3 className="card__title">Edit text and labels</h3>
                <p className="card__text">
                  "Change the room label from OFFICE to CONFERENCE" &mdash; update text entities
                  across your drawing without hunting through layers.
                </p>
              </article>
              <article className="card">
                <div className="card__icon" aria-hidden="true">&#10006;</div>
                <h3 className="card__title">Delete elements</h3>
                <p className="card__text">
                  "Remove the staircase on layer STAIRS" &mdash; cleanly delete entities by
                  description, layer, or type. Protected layers stay safe.
                </p>
              </article>
            </div>
          </div>
        </section>

        <section style={{ padding: 'var(--space-7) 0' }}>
          <div className="container container--narrow" style={{ textAlign: 'center' }}>
            <h2 style={{ marginBottom: 'var(--space-6)' }}>How it works</h2>
            <div className="flex flex-col gap-5" style={{ textAlign: 'left' }}>
              <div className="flex gap-4 items-center">
                <div style={{
                  minWidth: '40px', height: '40px', borderRadius: 'var(--radius-full)',
                  background: 'var(--accent-primary)', color: 'white',
                  display: 'grid', placeItems: 'center', fontFamily: 'var(--font-display)', fontWeight: 700
                }}>1</div>
                <div>
                  <h4 style={{ marginBottom: 'var(--space-1)' }}>Upload your file</h4>
                  <p className="text-sm text-secondary">Drag and drop a .dxf or .pdf file. We convert and analyze it automatically.</p>
                </div>
              </div>
              <div className="flex gap-4 items-center">
                <div style={{
                  minWidth: '40px', height: '40px', borderRadius: 'var(--radius-full)',
                  background: 'var(--accent-primary)', color: 'white',
                  display: 'grid', placeItems: 'center', fontFamily: 'var(--font-display)', fontWeight: 700
                }}>2</div>
                <div>
                  <h4 style={{ marginBottom: 'var(--space-1)' }}>Describe the change</h4>
                  <p className="text-sm text-secondary">Tell the AI what to edit in plain language. It plans the operations and validates them.</p>
                </div>
              </div>
              <div className="flex gap-4 items-center">
                <div style={{
                  minWidth: '40px', height: '40px', borderRadius: 'var(--radius-full)',
                  background: 'var(--accent-primary)', color: 'white',
                  display: 'grid', placeItems: 'center', fontFamily: 'var(--font-display)', fontWeight: 700
                }}>3</div>
                <div>
                  <h4 style={{ marginBottom: 'var(--space-1)' }}>Review and download</h4>
                  <p className="text-sm text-secondary">See a visual before/after preview. Select which changes to keep, then download the edited file.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section style={{ padding: 'var(--space-7) 0', background: 'var(--bg-secondary)' }}>
          <div className="container" style={{ textAlign: 'center', maxWidth: '600px' }}>
            <h2 style={{ marginBottom: 'var(--space-3)' }}>Ready to start?</h2>
            <p className="text-secondary" style={{ marginBottom: 'var(--space-5)' }}>
              No install required. Works in your browser.
            </p>
            <div className="flex gap-4 justify-center" style={{ flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn btn--primary btn--lg"
                onClick={handleTryNow}
                disabled={trying}
              >
                {trying ? 'Loading...' : 'Try It Now'}
              </button>
              <Link to="/login" className="btn btn--secondary btn--lg">
                Create Account
              </Link>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
