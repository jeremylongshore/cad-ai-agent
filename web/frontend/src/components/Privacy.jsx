import { Link } from 'react-router-dom';
import Footer from './Footer';

export default function Privacy() {
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

      <main style={{ flex: 1, padding: 'var(--space-7) 0' }}>
        <div className="container container--narrow">
          <h1 style={{ marginBottom: 'var(--space-5)' }}>Privacy Policy</h1>
          <p className="text-sm text-tertiary" style={{ marginBottom: 'var(--space-5)' }}>Last updated: February 24, 2026</p>

          <div className="flex flex-col gap-5" style={{ lineHeight: 1.8, color: 'var(--text-secondary)' }}>
            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Who We Are</h3>
              <p>CAD DXF Agent is operated by <a href="https://intentsolutions.io" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-primary)' }}>Intent Solutions</a>. Contact us at <a href="mailto:jeremy@intentsolutions.io" style={{ color: 'var(--accent-primary)' }}>jeremy@intentsolutions.io</a> for any privacy-related requests.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Information We Collect</h3>
              <p>When you use CAD DXF Agent, we collect:</p>
              <ul style={{ paddingLeft: 'var(--space-5)', listStyle: 'disc', marginTop: 'var(--space-2)' }}>
                <li><strong>Account information:</strong> Name, email address, and encrypted credentials when you sign up.</li>
                <li><strong>Uploaded files:</strong> DXF and PDF files you upload for editing. These are stored temporarily in session memory and deleted after 2 hours or when you end your session.</li>
                <li><strong>Usage data:</strong> Device info, IP address, and usage analytics collected automatically.</li>
              </ul>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>How We Use Your Information</h3>
              <p>Your data is used exclusively to provide the CAD editing service. We do NOT sell, rent, or share your personal information or uploaded files with third parties for marketing purposes.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>File Handling</h3>
              <p>Uploaded DXF and PDF files are processed in temporary server memory. Files are automatically deleted after 2 hours. We do not retain copies of your CAD drawings beyond the active editing session.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Data Security</h3>
              <p>We use encryption, secure cloud infrastructure (Google Cloud Platform), bcrypt password hashing, and regular security audits. While we implement strong protections, no system is 100% secure.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Third-Party Services</h3>
              <ul style={{ paddingLeft: 'var(--space-5)', listStyle: 'disc', marginTop: 'var(--space-2)' }}>
                <li>Google Cloud Platform (hosting and AI processing)</li>
                <li>Firebase (authentication and hosting)</li>
                <li>Vertex AI (CAD edit planning via Gemini)</li>
              </ul>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Your Rights</h3>
              <p>You may request to review, delete, or modify your account data at any time by contacting <a href="mailto:jeremy@intentsolutions.io" style={{ color: 'var(--accent-primary)' }}>jeremy@intentsolutions.io</a>. Data will be deleted within 30 days of a valid request.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Changes to This Policy</h3>
              <p>We may update this policy and will notify you via email or through the service.</p>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
