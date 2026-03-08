/**
 * ActiveDrawingBadge — compact inline badge showing the active library document.
 *
 * Usage:
 *   <ActiveDrawingBadge filename="floor-plan-v3.dxf" />
 */

export default function ActiveDrawingBadge({ filename }) {
  if (!filename) return null;

  // Truncate long filenames
  const display = filename.length > 32 ? filename.slice(0, 29) + '...' : filename;

  return (
    <span
      title={filename}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: '2px 8px',
        background: 'var(--accent-success-light)',
        border: '1px solid var(--accent-success)',
        borderRadius: 'var(--radius-full)',
        fontSize: 'var(--text-xs)',
        fontWeight: 500,
        color: 'var(--accent-success)',
        maxWidth: 240,
        overflow: 'hidden',
        whiteSpace: 'nowrap',
        textOverflow: 'ellipsis',
      }}
    >
      {/* Green live dot */}
      <span
        aria-hidden="true"
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: 'var(--accent-success)',
          flexShrink: 0,
        }}
      />
      {display}
    </span>
  );
}
