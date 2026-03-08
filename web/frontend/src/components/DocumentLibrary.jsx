import DocumentCard from './DocumentCard';
import DocumentUploadButton from './DocumentUploadButton';
import StorageIndicator from './StorageIndicator';

/**
 * DocumentLibrary — sidebar panel listing user's persisted DXF documents.
 *
 * Usage:
 *   <DocumentLibrary
 *     documents={documents}
 *     activeDocumentId={activeDocumentId}
 *     storageUsage={storageUsage}
 *     loading={libraryLoading}
 *     error={libraryError}
 *     onUpload={uploadToLibrary}
 *     onLoad={loadFromLibrary}
 *     onDelete={deleteFromLibrary}
 *     onClearError={clearLibraryError}
 *     onCompareOpen={() => setCompareOpen(true)}
 *   />
 */

export default function DocumentLibrary({
  documents,
  activeDocumentId,
  storageUsage,
  loading,
  error,
  onUpload,
  onLoad,
  onDelete,
  onClearError,
  onCompareOpen,
}) {
  const atQuota =
    storageUsage &&
    storageUsage.document_count >= storageUsage.document_limit;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      minHeight: 0,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-3) var(--space-3) var(--space-2)',
        borderBottom: '1px solid var(--border-default)',
        flexShrink: 0,
      }}>
        <h3 style={{
          fontSize: 'var(--text-xs)',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.07em',
          color: 'var(--text-tertiary)',
          margin: 0,
        }}>
          Documents
        </h3>
        <div style={{ display: 'flex', gap: 'var(--space-1)', alignItems: 'center' }}>
          {loading && (
            <span
              className="spinner"
              aria-hidden="true"
              style={{ width: 12, height: 12, borderWidth: 1.5 }}
            />
          )}
          <DocumentUploadButton
            onUpload={onUpload}
            loading={loading}
            atQuota={atQuota}
          />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-2) var(--space-3)',
          background: 'var(--accent-danger-light)',
          borderBottom: '1px solid var(--border-default)',
          flexShrink: 0,
          gap: 'var(--space-2)',
        }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--accent-danger)', flex: 1 }}>
            {error}
          </span>
          <button
            className="btn btn--ghost btn--sm"
            onClick={onClearError}
            aria-label="Dismiss error"
            style={{ padding: '1px 4px', color: 'var(--accent-danger)', cursor: 'pointer' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* Document list */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: 'var(--space-2) var(--space-2)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-1)',
      }}>
        {documents.length === 0 && !loading && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            flex: 1,
            padding: 'var(--space-6) var(--space-3)',
            textAlign: 'center',
            color: 'var(--text-tertiary)',
          }}>
            {/* Folder icon */}
            <svg
              width="32" height="32" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
              strokeLinejoin="round" aria-hidden="true"
              style={{ marginBottom: 'var(--space-2)', opacity: 0.5 }}
            >
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <p style={{ fontSize: 'var(--text-xs)', margin: 0 }}>
              No saved documents.
              <br />
              Upload a .dxf to your library.
            </p>
          </div>
        )}

        {documents.map((doc) => (
          <DocumentCard
            key={doc.doc_id}
            doc={doc}
            isActive={activeDocumentId === doc.doc_id}
            onLoad={onLoad}
            onDelete={onDelete}
          />
        ))}
      </div>

      {/* Compare from library button (only visible when 2+ documents exist) */}
      {documents.length >= 2 && onCompareOpen && (
        <div style={{
          padding: 'var(--space-2) var(--space-2)',
          borderTop: '1px solid var(--border-default)',
          flexShrink: 0,
        }}>
          <button
            className="btn btn--ghost btn--sm btn--full"
            onClick={onCompareOpen}
            style={{ justifyContent: 'flex-start', gap: 'var(--space-2)', cursor: 'pointer' }}
          >
            {/* Diff icon */}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="18" cy="18" r="3" />
              <circle cx="6" cy="6" r="3" />
              <path d="M13 6h3a2 2 0 0 1 2 2v7" />
              <line x1="6" y1="9" x2="6" y2="21" />
            </svg>
            Compare from library
          </button>
        </div>
      )}

      {/* Storage indicator at the bottom */}
      <div style={{ borderTop: '1px solid var(--border-default)', flexShrink: 0 }}>
        <StorageIndicator usage={storageUsage} />
      </div>
    </div>
  );
}
