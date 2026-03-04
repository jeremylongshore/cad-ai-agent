import { useRef } from 'react';
import { useSession } from '../hooks/useSession';
import FileUpload from './FileUpload';
import ChatPanel from './ChatPanel';
import PreviewPanel from './PreviewPanel';

export default function Workspace({ user, onSignOut }) {
  const session = useSession();
  const { fileInfo, sessionId, messages, operations, selectedOps, previewUrls, dxfUrls, comparisonResult, loading, loadingStartTime, error } = session;
  const replaceInputRef = useRef(null);

  return (
    <div className="page" style={{ height: '100vh', overflow: 'hidden' }}>
      <header className="site-header">
        <div className="container--wide site-header__inner" style={{ paddingInline: 'var(--space-4)' }}>
          <div className="site-header__logo">
            <div className="site-header__logo-icon" aria-hidden="true">C</div>
            <span className="hide-mobile">CAD DXF Agent</span>
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
        <main className="flex items-center justify-center" style={{ flex: 1 }}>
          <div className="container container--narrow">
            <h2 style={{ textAlign: 'center', marginBottom: 'var(--space-5)' }}>
              Upload a drawing to get started
            </h2>
            <FileUpload onUpload={session.upload} loading={loading} />
          </div>
        </main>
      ) : (
        <div className="workspace">
          <div className={`workspace__upload-bar${fileInfo ? ' workspace__upload-bar--compact' : ''}`}>
            {fileInfo ? (
              <div className="upload-bar-compact">
                <span className="upload-bar-compact__filename">{fileInfo.filename}</span>
                <span className="upload-bar-compact__meta">
                  {fileInfo.entity_count} entities &middot; {fileInfo.layer_count} layers
                </span>
                <button
                  className="btn btn--ghost btn--sm"
                  onClick={() => replaceInputRef.current?.click()}
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

          <aside className="workspace__sidebar" aria-label="File information">
            {fileInfo && (
              <div className="file-info">
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
            />
          </aside>
        </div>
      )}
    </div>
  );
}
