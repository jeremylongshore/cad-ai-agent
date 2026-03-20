import { useRef, useState, useEffect, useCallback } from 'react';
import { useSession } from '../hooks/useSession';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';
import { entitiesNear } from '../lib/api';
import FileUpload from './FileUpload';
import ChatPanel from './ChatPanel';
import PreviewPanel from './PreviewPanel';
import DocumentLibrary from './DocumentLibrary';
import ActiveDrawingBadge from './ActiveDrawingBadge';
import CompareFromLibrary from './CompareFromLibrary';

export default function Workspace({ user, onSignOut }) {
  const session = useSession();
  const { fileInfo, sessionId, messages, operations, selectedOps, previewUrls, dxfUrls, comparisonResult, loading, loadingStartTime, error } = session;
  const replaceInputRef = useRef(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [compareLibraryOpen, setCompareLibraryOpen] = useState(false);
  const [selectedEntities, setSelectedEntities] = useState([]);

  const isAuthenticated = !!user;
  const library = useDocumentLibrary(isAuthenticated);
  const [reconnectFailed, setReconnectFailed] = useState(false);
  const reconnectAttemptsRef = useRef(0);

  // Attempt to reconnect a previously active library session on mount
  useEffect(() => {
    if (!isAuthenticated) return;
    library.tryReconnect().then((data) => {
      if (data && data.session_id) {
        const savedDocId = localStorage.getItem('intentcad_active_document_id');
        session.loadFromLibraryData(data, savedDocId);
        setReconnectFailed(false);
      }
    }).catch(() => {
      reconnectAttemptsRef.current += 1;
      if (reconnectAttemptsRef.current >= 3) {
        setReconnectFailed(true);
      }
    });
    // Intentionally omit library and session from deps — run once on auth
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  // Auto-collapse sidebar when file is uploaded (compact bar already shows info)
  useEffect(() => {
    if (fileInfo) setSidebarCollapsed(true);
  }, [fileInfo]);

  // Load a document from the library into the active session
  const handleLibraryLoad = useCallback(async (docId) => {
    try {
      const data = await library.loadFromLibrary(docId);
      await session.loadFromLibraryData(data, docId);
    } catch (err) {
      // error is surfaced via library.libraryError
    }
  }, [library, session]);

  // Compare two library documents (result flows into session's comparisonResult)
  const handleLibraryCompare = useCallback(async (masterDocId, revisionDocId, profile) => {
    const data = await library.compareDocuments(masterDocId, revisionDocId, profile);
    // Surface the result in the session's comparison UI
    session.compareRevision && console.info('[cad] Library compare result:', data);
    return data;
  }, [library, session]);

  // Entity selection via viewer click
  const handleEntityClick = useCallback(async (position, ctrlKey) => {
    if (!sessionId) return;
    try {
      const res = await entitiesNear(sessionId, position.x, position.y);
      if (!res.entities?.length) return;
      const entity = res.entities[0];

      if (ctrlKey) {
        setSelectedEntities(prev => {
          const exists = prev.find(e => e.handle === entity.handle);
          if (exists) return prev.filter(e => e.handle !== entity.handle);
          return [...prev, entity];
        });
      } else {
        setSelectedEntities([entity]);
      }
    } catch (err) {
      console.error('Entity pick failed:', err);
    }
  }, [sessionId]);

  const handleRemoveEntity = useCallback((handle) => {
    setSelectedEntities(prev => prev.filter(e => e.handle !== handle));
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedEntities([]);
  }, []);

  return (
    <div className="page" style={{ height: '100vh', overflow: 'hidden' }}>
      <header className="site-header">
        <div className="container--wide site-header__inner" style={{ paddingInline: 'var(--space-4)' }}>
          <div className="site-header__logo">
            <div className="site-header__logo-icon" aria-hidden="true">I</div>
            <span className="hide-mobile">IntentCAD</span>
          </div>
          <div className="flex items-center gap-3">
            {sessionId && (
              <button className="btn btn--ghost btn--sm" onClick={session.reset}>
                New File
              </button>
            )}
            <span className="text-sm text-secondary hide-mobile">
              {user.email}
            </span>
            <button className="btn btn--ghost btn--sm" onClick={onSignOut}>
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {reconnectFailed && (
        <div style={{ background: 'var(--accent-warning-light, #332b00)', padding: 'var(--space-2) var(--space-4)', borderBottom: '1px solid var(--accent-warning, #b38600)' }}>
          <div className="container--wide flex justify-between items-center">
            <span className="text-sm" style={{ color: 'var(--accent-warning, #b38600)' }}>
              Connection lost. Unable to reach the server.
            </span>
            <button
              className="btn btn--ghost btn--sm"
              onClick={() => { setReconnectFailed(false); reconnectAttemptsRef.current = 0; window.location.reload(); }}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {error && (
        <div style={{ background: 'var(--accent-danger-light)', padding: 'var(--space-2) var(--space-4)', borderBottom: '1px solid var(--accent-danger)' }}>
          <div className="container--wide flex justify-between items-center">
            <span className="text-sm" style={{ color: 'var(--accent-danger)' }}>{error}</span>
            <button className="btn btn--ghost btn--sm" onClick={session.clearError} aria-label="Dismiss error">
              &#10005;
            </button>
          </div>
        </div>
      )}

      {!sessionId ? (
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden', height: 'calc(100vh - 57px)' }}>
          {/* Library sidebar on the empty state too */}
          <aside
            style={{
              width: 240,
              borderRight: '1px solid var(--border-default)',
              background: 'var(--bg-primary)',
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
            aria-label="Document library"
          >
            <DocumentLibrary
              documents={library.documents}
              activeDocumentId={library.activeDocumentId}
              storageUsage={library.storageUsage}
              loading={library.libraryLoading}
              error={library.libraryError}
              onUpload={library.uploadToLibrary}
              onLoad={handleLibraryLoad}
              onDelete={library.deleteFromLibrary}
              onClearError={library.clearLibraryError}
              onCompareOpen={library.documents.length >= 2 ? () => setCompareLibraryOpen(true) : null}
            />
          </aside>

          <main className="flex items-center justify-center" style={{ flex: 1 }}>
            <div className="container container--narrow">
              <h2 style={{ textAlign: 'center', marginBottom: 'var(--space-5)' }}>
                Upload a drawing to get started
              </h2>
              <FileUpload onUpload={session.upload} loading={loading} />
            </div>
          </main>
        </div>
      ) : (
        <div className={`workspace${sidebarCollapsed ? ' workspace--sidebar-collapsed' : ''}`}>
          <div className={`workspace__upload-bar${fileInfo ? ' workspace__upload-bar--compact' : ''}`}>
            {fileInfo ? (
              <div className="upload-bar-compact">
                <span className="upload-bar-compact__filename">{fileInfo.filename}</span>
                <span className="upload-bar-compact__meta">
                  {fileInfo.entity_count} entities &middot; {fileInfo.layer_count} layers
                </span>
                {/* Show badge when document came from library */}
                {session.documentId && (
                  <ActiveDrawingBadge filename={fileInfo.filename} />
                )}
                <button
                  className="btn btn--ghost btn--sm"
                  onClick={() => setSidebarCollapsed((c) => !c)}
                  title={sidebarCollapsed ? 'Show file info' : 'Hide file info'}
                  style={{ cursor: 'pointer' }}
                >
                  {sidebarCollapsed ? 'Info' : 'Hide Info'}
                </button>
                <button
                  className="btn btn--ghost btn--sm"
                  onClick={() => replaceInputRef.current?.click()}
                  style={{ cursor: 'pointer' }}
                >
                  Replace file
                </button>
                <input
                  ref={replaceInputRef}
                  type="file"
                  accept=".dxf,.dwg,.pdf"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) session.upload(file);
                    e.target.value = '';
                  }}
                  style={{ display: 'none' }}
                  aria-hidden="true"
                />
              </div>
            ) : (
              <FileUpload onUpload={session.upload} loading={loading} />
            )}
          </div>

          <aside className="workspace__sidebar" aria-label="Document library and file information">
            {/* Document library always visible in the sidebar.
                Negative margins cancel the sidebar's padding so the library
                can own its full-bleed layout (header border, scroll area, footer). */}
            <div style={{
              height: fileInfo ? '50%' : '100%',
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              margin: 'calc(-1 * var(--space-4)) calc(-1 * var(--space-4)) 0',
              borderBottom: fileInfo ? '1px solid var(--border-default)' : 'none',
            }}>
              <DocumentLibrary
                documents={library.documents}
                activeDocumentId={library.activeDocumentId}
                storageUsage={library.storageUsage}
                loading={library.libraryLoading}
                error={library.libraryError}
                onUpload={library.uploadToLibrary}
                onLoad={handleLibraryLoad}
                onDelete={library.deleteFromLibrary}
                onClearError={library.clearLibraryError}
                onCompareOpen={library.documents.length >= 2 ? () => setCompareLibraryOpen(true) : null}
              />
            </div>

            {/* File metadata — shown below the library when a file is active */}
            {fileInfo && (
              <div className="file-info" style={{ marginTop: 'var(--space-4)', paddingTop: 'var(--space-3)' }}>
                <div className="file-info__header">
                  <span className="file-info__name">{fileInfo.filename}</span>
                </div>
                <div className="file-info__stat">
                  <span>Entities</span>
                  <span className="file-info__stat-value">{fileInfo.entity_count}</span>
                </div>
                <div className="file-info__stat">
                  <span>Layers</span>
                  <span className="file-info__stat-value">{fileInfo.layer_count}</span>
                </div>
                {fileInfo.page_classifications && (
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <p className="text-xs text-tertiary" style={{ marginBottom: 'var(--space-1)' }}>Pages</p>
                    <div className="flex gap-1" style={{ flexWrap: 'wrap' }}>
                      {fileInfo.page_classifications.map((c) => (
                        <span
                          key={c.page}
                          className={`badge ${c.type === 'vector_layout' ? 'badge--success' : c.type === 'raster_scanned' ? 'badge--warning' : ''}`}
                          title={`${c.vectors} vectors, ${c.text} text`}
                        >
                          P{c.page}: {c.type.replace('_', ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {fileInfo.layers && (
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <p className="text-xs text-tertiary" style={{ marginBottom: 'var(--space-1)' }}>Layers</p>
                    <div className="flex gap-1" style={{ flexWrap: 'wrap' }}>
                      {fileInfo.layers.map((layer) => (
                        <span key={layer} className="badge">{layer}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </aside>

          <section className="workspace__main" aria-label="Drawing preview">
            <PreviewPanel
              previewUrls={previewUrls}
              dxfUrls={dxfUrls}
              operations={operations}
              selectedOps={selectedOps}
              onToggleOp={session.toggleOp}
              onApply={() => session.apply()}
              onDownload={session.download}
              onCompare={session.compareRevision}
              comparisonResult={comparisonResult}
              loading={loading}
              revisionOps={session.revisionOps}
              revisionFile={session.revisionFile}
              alignmentResult={session.alignmentResult}
              diffSummary={session.diffSummary}
              wizardStep={session.wizardStep}
              revisionApplyResult={session.revisionApplyResult}
              bundleReady={session.bundleReady}
              onRevisionUpload={session.handleRevisionUpload}
              onRevisionApproveOp={session.handleRevisionApproveOp}
              onRevisionBulkApprove={session.handleRevisionBulkApprove}
              onRevisionApply={session.handleRevisionApply}
              onBundleDownload={session.handleBundleDownload}
              onRealign={session.handleRealign}
              editPreview={session.editPreview}
              editApplyResult={session.editApplyResult}
              onPreviewPlan={session.previewPlan}
              onApprovePlan={session.approvePlan}
              onApproveAndApplyPlan={session.approveAndApplyPlan}
              onApplyPlan={session.applyPlan}
              onEntityClick={handleEntityClick}
              selectedEntities={selectedEntities}
            />
          </section>

          <aside className="workspace__chat" aria-label="Chat">
            <ChatPanel
              messages={messages}
              onSend={session.sendPrompt}
              onClear={session.clearConversation}
              onRetry={session.retryLastAi}
              loading={loading}
              loadingStartTime={loadingStartTime}
              disabled={!sessionId}
              hasOperations={operations.length > 0}
              hasEdited={!!previewUrls.edited}
              selectedEntities={selectedEntities}
              onRemoveEntity={handleRemoveEntity}
              onClearSelection={handleClearSelection}
            />
          </aside>
        </div>
      )}

      {/* Compare from Library modal */}
      {compareLibraryOpen && (
        <CompareFromLibrary
          documents={library.documents}
          onCompare={handleLibraryCompare}
          onClose={() => setCompareLibraryOpen(false)}
        />
      )}
    </div>
  );
}
