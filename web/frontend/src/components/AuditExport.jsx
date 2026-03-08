import { useCallback, useState } from 'react';

/**
 * AuditExport — download precision_actions as a JSON audit file.
 *
 * Creates a Blob from the actions array and triggers a browser download.
 * Filename: precision-audit-{ISO-timestamp}.json
 *
 * Usage:
 *   <AuditExport actions={precisionActions} />
 *
 * Props:
 *   actions — array of action detail objects (same shape as ActionDetailView)
 */
export default function AuditExport({ actions }) {
  const [downloaded, setDownloaded] = useState(false);

  const handleExport = useCallback(() => {
    if (!actions || actions.length === 0) return;

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `precision-audit-${timestamp}.json`;

    const payload = {
      exported_at: new Date().toISOString(),
      action_count: actions.length,
      actions,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    setDownloaded(true);
    setTimeout(() => setDownloaded(false), 2000);
  }, [actions]);

  const disabled = !actions || actions.length === 0;

  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm"
      onClick={handleExport}
      disabled={disabled}
      aria-label="Export precision audit log as JSON"
      title={disabled ? 'No precision actions to export' : `Export ${actions.length} action(s) as JSON`}
    >
      {downloaded ? 'Downloaded' : 'Export Audit'}
    </button>
  );
}
