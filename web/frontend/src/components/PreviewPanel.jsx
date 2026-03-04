import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchProfiles } from '../lib/api';
import DxfViewerComponent from './DxfViewerComponent';

const TABS = [
  { key: 'original', label: 'Original' },
  { key: 'edited', label: 'Edited' },
  { key: 'comparison', label: 'Compare' },
];

const isOpApproved = (op) =>
  op.status === 'approved' || op.status === 'auto_approved' || op.status === 'force_approved';

const ALIGNMENT_LABELS = {
  identity: 'Identity',
  translation: 'Translation',
  rigid: 'Rigid',
  anchor: 'Anchor',
  feature: 'Feature',
  manual: 'Manual',
};

export default function PreviewPanel({
  previewUrls,
  dxfUrls,
  operations,
  selectedOps,
  onToggleOp,
  onApply,
  onDownload,
  onCompare,
  comparisonResult,
  loading,
  revisionOps,
  revisionFile,
  alignmentResult,
  diffSummary,
  wizardStep,
  revisionApplyResult,
  bundleReady,
  onRevisionUpload,
  onRevisionApproveOp,
  onRevisionBulkApprove,
  onRevisionApply,
  onBundleDownload,
}) {
  const [activeTab, setActiveTab] = useState('original');
  const hasEdited = !!previewUrls.edited;
  const hasOperations = operations.length > 0;
  const revisionInputRef = useRef(null);
  const [profileNames, setProfileNames] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [focusedOpIndex, setFocusedOpIndex] = useState(-1);
  const opsListRef = useRef(null);

  useEffect(() => {
    if (previewUrls.edited) setActiveTab('edited');
  }, [previewUrls.edited]);

  useEffect(() => {
    if (revisionOps && revisionOps.length > 0) setActiveTab('comparison');
  }, [revisionOps]);

  useEffect(() => {
    fetchProfiles()
      .then((data) => setProfileNames(Object.keys(data)))
      .catch((err) => console.error('Failed to fetch profiles:', err));
  }, []);

  // Auto-focus first op when diff loads (a11y: cad-du8.7)
  useEffect(() => {
    if (revisionOps && revisionOps.length > 0 && focusedOpIndex === -1) {
      setFocusedOpIndex(0);
    }
  }, [revisionOps, focusedOpIndex]);

  const handleRevisionUpload = (e) => {
    const file = e.target.files?.[0];
    if (file && onRevisionUpload) {
      onRevisionUpload(file, selectedProfile || null);
    }
    if (revisionInputRef.current) revisionInputRef.current.value = '';
  };

  // Legacy compare handler for simple compare flow
  const handleSimpleCompare = (e) => {
    const file = e.target.files?.[0];
    if (file && onCompare) {
      onCompare(file, selectedProfile || null);
    }
    if (revisionInputRef.current) revisionInputRef.current.value = '';
  };

  // Keyboard navigation for review list (cad-du8.7)
  const handleOpsKeyDown = useCallback((e) => {
    if (!revisionOps || revisionOps.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedOpIndex((prev) => Math.min(prev + 1, revisionOps.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedOpIndex((prev) => Math.max(prev - 1, 0));
    } else if ((e.key === 'Enter' || e.key === ' ') && focusedOpIndex >= 0) {
      e.preventDefault();
      const op = revisionOps[focusedOpIndex];
      if (op && onRevisionApproveOp) {
        const newAction = op.status === 'approved' || op.status === 'auto_approved' ? 'reject' : 'approve';
        onRevisionApproveOp(op.op_id, newAction);
      }
    }
  }, [revisionOps, focusedOpIndex, onRevisionApproveOp]);

  // Focus the active op item when focusedOpIndex changes
  useEffect(() => {
    if (opsListRef.current && focusedOpIndex >= 0) {
      const items = opsListRef.current.querySelectorAll('[role="listitem"]');
      if (items[focusedOpIndex]) {
        items[focusedOpIndex].focus();
      }
    }
  }, [focusedOpIndex]);

  // Use wizard upload if available, else fallback to simple compare
  const useWizard = !!onRevisionUpload;

  return (
    <div className="preview">
      <div className="preview__tabs" role="tablist" aria-label="Preview views">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`preview__tab${activeTab === tab.key ? ' preview__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="preview__image-wrap" role="tabpanel" aria-label={`${activeTab} preview`}>
        {activeTab === 'comparison' && dxfUrls?.original && dxfUrls?.comparison ? (
          <div className="compare-split">
            <div className="compare-split__pane">
              <span className="compare-split__label">Original</span>
              <DxfViewerComponent dxfUrl={dxfUrls.original} />
            </div>
            <div className="compare-split__pane">
              <span className="compare-split__label">Changes</span>
              <DxfViewerComponent dxfUrl={dxfUrls.comparison} />
            </div>
          </div>
        ) : dxfUrls?.[activeTab] ? (
          <DxfViewerComponent dxfUrl={dxfUrls[activeTab]} />
        ) : previewUrls[activeTab] ? (
          <img
            src={previewUrls[activeTab]}
            alt={`${activeTab} drawing preview`}
            loading="lazy"
          />
        ) : (
          <div className="preview__placeholder">
            {activeTab === 'original'
              ? 'Upload a file to see the preview'
              : activeTab === 'comparison'
                ? 'Upload a revision file to compare against the original'
                : 'Run an edit to see the result'}
          </div>
        )}
      </div>

      {/* ===== COMPARISON TAB CONTENT ===== */}
      {activeTab === 'comparison' && (
        <>
          {/* Step 1: Profile selector + upload (cad-du8.3) */}
          {(!revisionOps || revisionOps.length === 0) && !bundleReady && (
            <div className="wizard-step">
              <h4 className="op-list__title">Step 1: Upload Revision</h4>
              {profileNames.length > 0 && (
                <div className="input-group" style={{ marginBottom: 'var(--space-2)' }}>
                  <label className="input-group__label" htmlFor="profile-select">
                    Comparison Profile
                  </label>
                  <select
                    id="profile-select"
                    className="input-group__field"
                    value={selectedProfile}
                    onChange={(e) => setSelectedProfile(e.target.value)}
                  >
                    <option value="">All entities (no filter)</option>
                    {profileNames.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                  <span className="input-group__hint">
                    {selectedProfile === 'structural'
                      ? 'Lines, polylines, circles, arcs, blocks only — excludes title/notes'
                      : selectedProfile
                        ? `Filter: ${selectedProfile}`
                        : 'Compare all entities on all layers'}
                  </span>
                </div>
              )}
              <input
                ref={revisionInputRef}
                type="file"
                accept=".dxf,.dwg"
                onChange={useWizard ? handleRevisionUpload : handleSimpleCompare}
                style={{ display: 'none' }}
                id="revision-upload"
                aria-label="Upload revision file"
              />
              <button
                className="btn btn--secondary btn--full"
                onClick={() => revisionInputRef.current?.click()}
                disabled={loading}
              >
                {loading ? <span className="spinner" aria-hidden="true" /> : 'Upload Revision (.dxf / .dwg)'}
              </button>
              {revisionFile && (
                <p className="wizard-step__file-info">
                  Uploaded: {revisionFile}
                </p>
              )}
            </div>
          )}

          {/* Step 2: Alignment preview (cad-du8.4 / cad-31i.8) */}
          {alignmentResult && wizardStep >= 2 && (
            <div className="wizard-step">
              <h4 className="op-list__title">Step 2: Alignment</h4>
              <div className="alignment-info">
                <span className={`badge ${alignmentResult.confidence >= 0.7 ? 'badge--success' : 'badge--warning'}`}>
                  {ALIGNMENT_LABELS[alignmentResult.method] || alignmentResult.method}
                </span>
                <div className="alignment-info__metrics">
                  <div className="alignment-info__metric">
                    <span className="alignment-info__label">Confidence</span>
                    <div className="confidence-bar">
                      <div
                        className="confidence-bar__fill"
                        style={{ width: `${(alignmentResult.confidence * 100).toFixed(0)}%` }}
                        role="progressbar"
                        aria-valuenow={Math.round(alignmentResult.confidence * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`Alignment confidence: ${Math.round(alignmentResult.confidence * 100)}%`}
                      />
                    </div>
                    <span className="alignment-info__value">
                      {(alignmentResult.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  {(alignmentResult.translation[0] !== 0 || alignmentResult.translation[1] !== 0) && (
                    <div className="alignment-info__metric">
                      <span className="alignment-info__label">Translation</span>
                      <span className="alignment-info__value">
                        ({alignmentResult.translation[0].toFixed(1)}, {alignmentResult.translation[1].toFixed(1)})
                      </span>
                    </div>
                  )}
                  {alignmentResult.rotation_deg !== 0 && (
                    <div className="alignment-info__metric">
                      <span className="alignment-info__label">Rotation</span>
                      <span className="alignment-info__value">
                        {alignmentResult.rotation_deg.toFixed(2)}&deg;
                      </span>
                    </div>
                  )}
                </div>
                {alignmentResult.confidence < 0.7 && (
                  <p className="alignment-info__warning">
                    Low confidence alignment. Results may be inaccurate — consider providing control points.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Comparison summary badges */}
          {comparisonResult && comparisonResult.summary && (
            <div className="comparison-summary">
              <h4 className="op-list__title">
                {diffSummary ? diffSummary.headline : 'Comparison Results'}
              </h4>
              <div className="comparison-summary__grid">
                {comparisonResult.summary.added > 0 && (
                  <span className="comparison-badge comparison-badge--added">
                    +{comparisonResult.summary.added} added
                  </span>
                )}
                {comparisonResult.summary.removed > 0 && (
                  <span className="comparison-badge comparison-badge--removed">
                    -{comparisonResult.summary.removed} removed
                  </span>
                )}
                {comparisonResult.summary.modified > 0 && (
                  <span className="comparison-badge comparison-badge--modified">
                    ~{comparisonResult.summary.modified} modified
                  </span>
                )}
                {comparisonResult.summary.moved > 0 && (
                  <span className="comparison-badge comparison-badge--moved">
                    &rarr;{comparisonResult.summary.moved} moved
                  </span>
                )}
                {comparisonResult.total_changes === 0 && (
                  <span className="comparison-badge">No changes detected</span>
                )}
              </div>
            </div>
          )}

          {/* Step 3: Review & approve ops (cad-du8.5 / cad-du8.7) */}
          {revisionOps && revisionOps.length > 0 && !bundleReady && (
            <div className="wizard-step">
              <h4 className="op-list__title">Step 3: Review Changes</h4>

              {/* Bulk actions */}
              <div className="revision-bulk-actions">
                <button
                  className="btn btn--sm btn--secondary"
                  onClick={() => onRevisionBulkApprove('approve')}
                  disabled={loading}
                >
                  Approve All
                </button>
                <button
                  className="btn btn--sm btn--ghost"
                  onClick={() => onRevisionBulkApprove('reject')}
                  disabled={loading}
                >
                  Reject All
                </button>
              </div>

              {/* Status counts */}
              <div className="revision-apply__summary" aria-live="polite">
                <span className="comparison-badge comparison-badge--added">
                  {revisionOps.filter((o) => isOpApproved(o)).length} approved
                </span>
                {revisionOps.filter((o) => o.status === 'pending').length > 0 && (
                  <span className="comparison-badge">
                    {revisionOps.filter((o) => o.status === 'pending').length} pending
                  </span>
                )}
                {revisionOps.filter((o) => o.status === 'rejected').length > 0 && (
                  <span className="comparison-badge comparison-badge--removed">
                    {revisionOps.filter((o) => o.status === 'rejected').length} rejected
                  </span>
                )}
              </div>

              {/* Individual ops list */}
              <div
                className="revision-ops-list"
                ref={opsListRef}
                role="list"
                aria-label="Revision operations"
                onKeyDown={handleOpsKeyDown}
              >
                {revisionOps.map((op, i) => {
                  const isApproved = isOpApproved(op);
                  const isRejected = op.status === 'rejected';
                  const isFocused = focusedOpIndex === i;
                  return (
                    <div
                      key={op.op_id}
                      role="listitem"
                      tabIndex={isFocused ? 0 : -1}
                      className={`revision-op-item${isFocused ? ' revision-op-item--focused' : ''}`}
                      aria-label={`${op.op_type} ${op.description}: ${op.status}`}
                      onClick={() => setFocusedOpIndex(i)}
                    >
                      <div className="revision-op-item__header">
                        <span className={`op-item__type op-item__type--${opTypeClass(op.op_type)}`}>
                          {op.op_type}
                        </span>
                        <span className="revision-op-item__confidence" title="Match confidence">
                          {(op.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="revision-op-item__desc">{op.description}</p>
                      <div className="revision-op-item__actions">
                        <button
                          className={`btn btn--sm ${isApproved ? 'btn--primary' : 'btn--secondary'}`}
                          onClick={(e) => { e.stopPropagation(); onRevisionApproveOp(op.op_id, 'approve'); }}
                          disabled={loading}
                          aria-pressed={isApproved}
                        >
                          {isApproved ? 'Approved' : 'Approve'}
                        </button>
                        <button
                          className={`btn btn--sm ${isRejected ? 'btn--danger' : 'btn--ghost'}`}
                          onClick={(e) => { e.stopPropagation(); onRevisionApproveOp(op.op_id, 'reject'); }}
                          disabled={loading}
                          aria-pressed={isRejected}
                        >
                          {isRejected ? 'Rejected' : 'Reject'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Apply button — enabled only when no pending ops remain */}
              {(() => {
                const approved = revisionOps.filter((o) => isOpApproved(o)).length;
                const pending = revisionOps.filter((o) => o.status === 'pending').length;
                const canApply = approved > 0 && pending === 0;
                return (
                  <button
                    className="btn btn--primary btn--full"
                    onClick={onRevisionApply}
                    disabled={loading || !canApply}
                    style={{ marginTop: 'var(--space-2)' }}
                  >
                    {loading
                      ? <span className="spinner" aria-hidden="true" />
                      : canApply
                        ? `Apply ${approved} Approved Change${approved !== 1 ? 's' : ''}`
                        : 'Review all changes before applying'}
                  </button>
                );
              })()}
            </div>
          )}

          {/* Bundle download (post-apply) */}
          {bundleReady && revisionApplyResult && (
            <div className="bundle-download">
              <p className="bundle-download__status">
                Applied {revisionApplyResult.success_count} change(s) successfully
                {revisionApplyResult.failure_count > 0 && (
                  <span className="comparison-badge comparison-badge--removed" style={{ marginLeft: 'var(--space-2)' }}>
                    {revisionApplyResult.failure_count} failed
                  </span>
                )}
              </p>
              <button
                className="btn btn--secondary btn--full bundle-download__link"
                onClick={onBundleDownload}
              >
                Download Bundle (.zip)
              </button>
              <p className="bundle-download__hint">
                Contains updated master DXF, diff overlay, changelog, alignment result, and metadata
              </p>
            </div>
          )}
        </>
      )}

      {/* ===== EDIT TAB CONTENT ===== */}
      {hasOperations && activeTab !== 'comparison' && (
        <div className="op-list">
          <h4 className="op-list__title">Planned operations</h4>
          {operations.map((op, i) => (
            <label key={i} className="op-item">
              <input
                type="checkbox"
                className="op-item__checkbox"
                checked={selectedOps.includes(i)}
                onChange={() => onToggleOp(i)}
              />
              <span className="op-item__text">{op.description || op.summary || `Operation ${i + 1}`}</span>
              <span className={`op-item__type op-item__type--${opTypeClass(op.op_type)}`}>
                {op.op_type}
              </span>
            </label>
          ))}
        </div>
      )}

      {hasOperations && activeTab !== 'comparison' && (
        <div className="flex gap-2">
          <button
            className="btn btn--primary btn--full"
            onClick={onApply}
            disabled={loading || selectedOps.length === 0}
          >
            {loading ? <span className="spinner" aria-hidden="true" /> : 'Apply Changes'}
          </button>
        </div>
      )}

      {hasEdited && (
        <button
          className="btn btn--secondary btn--full"
          onClick={onDownload}
          disabled={loading}
        >
          Download Edited DXF
        </button>
      )}
    </div>
  );
}

function opTypeClass(opType) {
  if (!opType) return 'edit';
  const t = opType.toLowerCase();
  if (t.includes('move')) return 'move';
  if (t.includes('delete') || t.includes('remove')) return 'delete';
  if (t.includes('add')) return 'add';
  return 'edit';
}
