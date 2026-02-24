export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="site-footer">
      <div className="container">
        <div className="site-footer__inner">
          <div className="site-footer__brand">
            <span className="site-footer__brand-name">CAD DXF Agent</span>
            <span className="site-footer__brand-tagline">
              AI-powered CAD editing by Intent Solutions
            </span>
          </div>

          <nav className="site-footer__links" aria-label="Footer navigation">
            <a
              href="https://intentsolutions.io"
              className="site-footer__link"
              target="_blank"
              rel="noopener noreferrer"
            >
              Intent Solutions
            </a>
            <a
              href="https://jeremylongshore.com"
              className="site-footer__link"
              target="_blank"
              rel="noopener noreferrer"
            >
              Jeremy Longshore
            </a>
            <a
              href="https://github.com/Intent-Solutions/cad-dxf-agent"
              className="site-footer__link"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
          </nav>
        </div>

        <div className="site-footer__bottom">
          <span className="site-footer__copy">
            &copy; {year} Intent Solutions. All rights reserved.
          </span>
          <nav className="site-footer__legal" aria-label="Legal">
            <a href="/privacy">Privacy Policy</a>
            <a href="/terms">Terms of Service</a>
          </nav>
        </div>
      </div>
    </footer>
  );
}
