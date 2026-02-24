import { Link } from 'react-router-dom';
import Footer from './Footer';

export default function Terms() {
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
          <h1 style={{ marginBottom: 'var(--space-5)' }}>Terms of Service</h1>
          <p className="text-sm text-tertiary" style={{ marginBottom: 'var(--space-5)' }}>Last updated: February 24, 2026</p>

          <div className="flex flex-col gap-5" style={{ lineHeight: 1.8, color: 'var(--text-secondary)' }}>
            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Service Description</h3>
              <p>CAD DXF Agent is an AI-powered CAD drawing editor operated by Intent Solutions. The service allows users to upload DXF and PDF files, describe edits in natural language, and download modified drawings.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Eligibility</h3>
              <p>You must be at least 18 years old to use this service. By creating an account, you represent that you have the authority to agree to these terms.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Your Content</h3>
              <p>You retain ownership of all files you upload. By using the service, you grant us a limited license to store, process, and render your files solely for the purpose of providing the editing service. We do not claim ownership of your drawings or use them for any other purpose.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Acceptable Use</h3>
              <p>You agree not to:</p>
              <ul style={{ paddingLeft: 'var(--space-5)', listStyle: 'disc', marginTop: 'var(--space-2)' }}>
                <li>Use the service for any unlawful purpose.</li>
                <li>Upload files containing malicious content.</li>
                <li>Attempt unauthorized access to the service or its systems.</li>
                <li>Reverse-engineer or interfere with the service&apos;s operation.</li>
              </ul>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Disclaimer</h3>
              <p>The service is provided &ldquo;AS IS&rdquo; without warranty. AI-generated edits should be reviewed by a qualified professional before use in construction or engineering applications. We are not liable for errors in AI-planned operations.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Limitation of Liability</h3>
              <p>Intent Solutions shall not be liable for any indirect, incidental, or consequential damages arising from use of the service. Our total liability shall not exceed the amount paid by you for the service in the preceding 12 months.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Termination</h3>
              <p>We reserve the right to suspend or terminate your account for violations of these terms. You may request deletion of your account and data at any time by contacting <a href="mailto:legal@intentsolutions.io" style={{ color: 'var(--accent-primary)' }}>legal@intentsolutions.io</a>.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Governing Law</h3>
              <p>These terms are governed by United States federal and state law where Intent Solutions operates.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Changes</h3>
              <p>We may update these terms and will notify users via email or through the service.</p>
            </section>

            <section>
              <h3 style={{ marginBottom: 'var(--space-2)' }}>Contact</h3>
              <p>For questions about these terms, contact <a href="mailto:legal@intentsolutions.io" style={{ color: 'var(--accent-primary)' }}>legal@intentsolutions.io</a>.</p>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
