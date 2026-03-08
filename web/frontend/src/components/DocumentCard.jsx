import { useState } from 'react';

/**
 * DocumentCard — a single document row in the library panel.
 *
 * Usage:
 *   <DocumentCard
 *     doc={{ doc_id, filename, uploaded_at, file_size_bytes }}
 *     isActive={activeDocumentId === doc.doc_id}
 *     onLoad={loadFromLibrary}
 *     onDelete={deleteFromLibrary}
 *   />
 */

function formatBytes(bytes) {
  if (bytes == null) return '';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function relativeTime(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function truncateFilename(name, max = 28) {
  if (!name || name.length <= max) return name;
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')) : '';
  return name.slice(0, max - ext.length - 1) + '…' + ext;
}

export default function DocumentCard({ doc, isActive, onLoad, onDelete }) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDeleteClick = (e) => {
    e.stopPropagation();
    if (confirmDelete) {
      onDelete(doc.doc_id);
      setConfirmDelete(false);
    } else {
      setConfirmDelete(true);
    }
  };

  const handleCardClick = () => {
    if (!isActive) onLoad(doc.doc_id);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleCardClick();
    }
  };

  return (
    <div
      className={`doc-card${isActive ? ' doc-card--active' : ''}`}
      onClick={handleCardClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-pressed={isActive}
      aria-label={`${doc.filename}${isActive ? ' (active)' : ''}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: 'var(--space-2) var(--space-3)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-default)',
        background: isActive ? 'var(--accent-primary-light)' : 'var(--bg-primary)',
        borderLeft: isActive ? '3px solid var(--accent-primary)' : '3px solid transparent',
        cursor: 'pointer',
        transition: 'all var(--transition-fast)',
        minWidth: 0,
      }}
      onMouseEnter={(e) => {
        if (!isActive) e.currentTarget.style.background = 'var(--bg-tertiary)';
      }}
      onMouseLeave={(e) => {
        if (!isActive) e.currentTarget.style.background = 'var(--bg-primary)';
      }}
      onFocus={(e) => {
        e.currentTarget.style.outline = '2px solid var(--border-focus)';
        e.currentTarget.style.outlineOffset = '2px';
      }}
      onBlur={(e) => {
        e.currentTarget.style.outline = 'none';
      }}
    >
      {/* DXF file icon */}
      <svg
        width="16" height="16" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round"
        strokeLinejoin="round" aria-hidden="true"
        style={{ flexShrink: 0, color: isActive ? 'var(--accent-primary)' : 'var(--text-tertiary)' }}
      >
        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
        <polyline points="13 2 13 9 20 9" />
      </svg>

      {/* Main content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--text-sm)',
          fontWeight: isActive ? 600 : 400,
          color: isActive ? 'var(--accent-primary)' : 'var(--text-primary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
          title={doc.filename}
        >
          {truncateFilename(doc.filename)}
        </div>
        <div style={{
          display: 'flex',
          gap: 'var(--space-2)',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-tertiary)',
          marginTop: 1,
        }}>
          <span>{relativeTime(doc.uploaded_at)}</span>
          {doc.file_size_bytes && (
            <>
              <span aria-hidden="true">&middot;</span>
              <span>{formatBytes(doc.file_size_bytes)}</span>
            </>
          )}
        </div>
      </div>

      {/* Delete button */}
      <button
        onClick={handleDeleteClick}
        onBlur={() => setConfirmDelete(false)}
        aria-label={confirmDelete ? `Confirm delete ${doc.filename}` : `Delete ${doc.filename}`}
        title={confirmDelete ? 'Click again to confirm' : 'Delete from library'}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 22,
          height: 22,
          flexShrink: 0,
          background: confirmDelete ? 'var(--accent-danger-light)' : 'none',
          border: confirmDelete ? '1px solid var(--accent-danger)' : '1px solid transparent',
          borderRadius: 'var(--radius-sm)',
          color: confirmDelete ? 'var(--accent-danger)' : 'var(--text-tertiary)',
          cursor: 'pointer',
          transition: 'all var(--transition-fast)',
          fontSize: 12,
          lineHeight: 1,
        }}
        onMouseEnter={(e) => {
          if (!confirmDelete) {
            e.currentTarget.style.color = 'var(--accent-danger)';
            e.currentTarget.style.background = 'var(--accent-danger-light)';
          }
        }}
        onMouseLeave={(e) => {
          if (!confirmDelete) {
            e.currentTarget.style.color = 'var(--text-tertiary)';
            e.currentTarget.style.background = 'none';
          }
        }}
      >
        {confirmDelete ? (
          /* Checkmark — confirm */
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : (
          /* X — delete */
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        )}
      </button>
    </div>
  );
}
