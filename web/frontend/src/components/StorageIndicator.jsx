/**
 * StorageIndicator — shows document count and storage usage as a progress bar.
 *
 * Usage:
 *   <StorageIndicator usage={storageUsage} />
 *
 * Expected `usage` shape (from /api/documents/usage):
 *   { document_count: 3, document_limit: 50, used_bytes: 12900000, storage_limit_bytes: 104857600 }
 */

function formatBytes(bytes) {
  if (bytes == null) return '—';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function StorageIndicator({ usage }) {
  if (!usage) return null;

  const {
    document_count: docCount = 0,
    document_limit: docLimit = 50,
    used_bytes: usedBytes = 0,
    storage_limit_bytes: limitBytes = 104857600,
  } = usage;

  const storagePct = limitBytes > 0 ? Math.min(100, (usedBytes / limitBytes) * 100) : 0;

  let barColor = 'var(--accent-success)';
  if (storagePct > 95) barColor = 'var(--accent-danger)';
  else if (storagePct > 80) barColor = 'var(--accent-warning)';

  return (
    <div style={{ padding: 'var(--space-3) var(--space-3) var(--space-2)' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: 'var(--space-1)',
      }}>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          {docCount} of {docLimit} docs
        </span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          {formatBytes(usedBytes)} / {formatBytes(limitBytes)}
        </span>
      </div>
      <div style={{
        height: 4,
        background: 'var(--bg-tertiary)',
        borderRadius: 'var(--radius-full)',
        overflow: 'hidden',
      }}
        role="progressbar"
        aria-valuenow={Math.round(storagePct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Storage: ${Math.round(storagePct)}% used`}
      >
        <div style={{
          height: '100%',
          width: `${storagePct}%`,
          background: barColor,
          borderRadius: 'var(--radius-full)',
          transition: 'width var(--transition-base)',
        }} />
      </div>
    </div>
  );
}
