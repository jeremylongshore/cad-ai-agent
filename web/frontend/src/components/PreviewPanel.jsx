import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
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

function RotateBar({ rotation, onRotate }) {
  return (
    <div className="rotate-bar">
      <button className="btn btn--ghost btn--sm" onClick={() => onRotate(-90)} title="Rotate left 90°">&#8634;</button>
      <span className="text-xs text-secondary">{rotation}°</span>
      <button className="btn btn--ghost btn--sm" onClick={() => onRotate(90)} title="Rotate right 90°">&#8635;</button>
    </div>
  );
}

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
  onRealign,
  editPreview,
  editApplyResult: structuredApplyResult,
  onPreviewPlan,
  onApprovePlan,
  onApproveAndApplyPlan,
  onApplyPlan,
  onEntityClick,
  selectedEntities,
}) {
  const [activeTab, setActiveTab] = useState('original');
  const hasEdited = !!previewUrls.edited;
  const hasOperations = operations.length > 0;
  const revisionInputRef = useRef(null);
  const [profileNames, setProfileNames] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [focusedOpIndex, setFocusedOpIndex] = useState(-1);
  const opsListRef = useRef(null);

  // Viewer refs for click-to-focus
  const activeViewerRef = useRef(null);
  const compareOriginalRef = useRef(null);
  const compareChangesRef = useRef(null);

  // Resize handle state for controls height
  const [controlsHeight, setControlsHeight] = useState(240);
  const dragStartRef = useRef(null);

  // Drawing rotation (degrees, multiples of 90)
  const [rotation, setRotation] = useState(0);
  const handleRotate = useCallback((deg) => setRotation((r) => (r + deg + 360) % 360), []);

  // Compare sub-view: 'split', 'original', 'revised'
  const [compareView, setCompareView] = useState('split');

  // Control point picker state
  const [pickingMode, setPickingMode] = useState(false);
  const [controlPoints, setControlPoints] = useState([]);
  // Each: { master: {x, y} | null, revision: {x, y} | null }
  const [currentPairSide, setCurrentPairSide] = useState('master'); // 'master' or 'revision'

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
      if (revisionOps?.length > 0 && !window.confirm('Replace current comparison? Your review progress will be lost.')) {
        if (revisionInputRef.current) revisionInputRef.current.value = '';
        return;
      }
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
        items[focusedOpIndex].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        items[focusedOpIndex].focus();
      }
    }
  }, [focusedOpIndex]);

  // Control point picking handlers
  const handleMasterPointClick = useCallback((pos) => {
    if (!pickingMode) return;
    setControlPoints((prev) => {
      const updated = [...prev];
      // Find first pair without a master point, or add new pair
      const incomplete = updated.findIndex((p) => !p.master);
      if (incomplete >= 0) {
        updated[incomplete] = { ...updated[incomplete], master: pos };
      } else if (updated.length < 4) {
        updated.push({ master: pos, revision: null });
      }
      return updated;
    });
    setCurrentPairSide('revision');
  }, [pickingMode]);

  const handleRevisionPointClick = useCallback((pos) => {
    if (!pickingMode) return;
    setControlPoints((prev) => {
      const updated = [...prev];
      // Find first pair with a master but no revision
      const incomplete = updated.findIndex((p) => p.master && !p.revision);
      if (incomplete >= 0) {
        updated[incomplete] = { ...updated[incomplete], revision: pos };
      }
      return updated;
    });
    setCurrentPairSide('master');
  }, [pickingMode]);

  const handleRealign = useCallback(() => {
    if (!onRealign) return;
    const pairs = controlPoints
      .filter((p) => p.master && p.revision)
      .map((p) => `${p.master.x.toFixed(2)},${p.master.y.toFixed(2)}:${p.revision.x.toFixed(2)},${p.revision.y.toFixed(2)}`);
    if (pairs.length > 0) {
      onRealign(pairs);
      setPickingMode(false);
    }
  }, [controlPoints, onRealign]);

  // Resize handle drag handlers
  const handleResizePointerDown = useCallback((e) => {
    e.preventDefault();
    e.target.setPointerCapture(e.pointerId);
    dragStartRef.current = { y: e.clientY, startHeight: controlsHeight };
  }, [controlsHeight]);

  const handleResizePointerMove = useCallback((e) => {
    if (!dragStartRef.current) return;
    const delta = dragStartRef.current.y - e.clientY; // drag up = grow controls
    const newHeight = Math.min(400, Math.max(80, dragStartRef.current.startHeight + delta));
    setControlsHeight(newHeight);
  }, []);

  const handleResizePointerUp = useCallback(() => {
    dragStartRef.current = null;
  }, []);

  const controlsStyle = useMemo(() => (
    activeTab === 'comparison' ? { maxHeight: controlsHeight, minHeight: controlsHeight } : undefined
  ), [activeTab, controlsHeight]);

  // Estimate a fallback radius from the viewer's current viewport (25% of camera height),
  // so the focus region scales with the drawing rather than being a fixed 100 units.
  const _viewportRadius = useCallback((viewerRef) => {
    const cam = viewerRef?.GetCamera?.();
    return cam ? cam.top / 4 : 100;
  }, []);

  // Click-to-focus: pan/zoom viewer to a revision op's location
  const handleFocusRevisionOp = useCallback((op) => {
    const bbox = op.bbox;
    let bounds = null;
    if (bbox) {
      bounds = { minX: bbox.min_x, minY: bbox.min_y, maxX: bbox.max_x, maxY: bbox.max_y };
    } else if (op.to_point || op.from_point) {
      const pt = op.to_point || op.from_point;
      const targetViewer = activeTab === 'comparison'
        ? (op.op_type === 'delete' ? compareOriginalRef.current : compareChangesRef.current)
        : activeViewerRef.current;
      const r = _viewportRadius(targetViewer);
      bounds = { minX: pt.x - r, minY: pt.y - r, maxX: pt.x + r, maxY: pt.y + r };
    }
    if (!bounds) return;

    if (activeTab === 'comparison') {
      const isMoveOrModify = ['move', 'modify_geometry', 'modify_text'].includes(op.op_type);

      if (op.op_type === 'delete' || isMoveOrModify) {
        compareOriginalRef.current?.focusOnBounds(bounds);
      }
      if (op.op_type !== 'delete') {
        compareChangesRef.current?.focusOnBounds(bounds);
      }
    } else {
      activeViewerRef.current?.focusOnBounds(bounds);
    }
  }, [activeTab, _viewportRadius]);

  // Click-to-focus: pan/zoom viewer to an edit preview op's location
  const handleFocusEditOp = useCallback((op) => {
    const pos = op.after_state?.position || op.after_state?.insert_point
              || op.before_state?.position || op.before_state?.insert_point;
    if (!pos) return;
    const r = _viewportRadius(activeViewerRef.current);
    const bounds = { minX: pos.x - r, minY: pos.y - r, maxX: pos.x + r, maxY: pos.y + r };
    activeViewerRef.current?.focusOnBounds(bounds);
  }, [_viewportRadius]);

  const completePairs = controlPoints.filter((p) => p.master && p.revision).length;

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

      {activeTab !== 'comparison' && <RotateBar rotation={rotation} onRotate={handleRotate} />}
      <div className="preview__image-wrap" role="tabpanel" aria-label={`${activeTab} preview`}>
        {activeTab === 'comparison' && dxfUrls?.original && dxfUrls?.comparison ? (
          <div className="compare-split-wrap">
            {/* Sub-tab bar: Split | Original | Revised */}
            <div className="compare-subtabs">
              {[
                { key: 'split', label: 'Split' },
                { key: 'original', label: 'Original' },
                { key: 'revised', label: 'Revised' },
              ].map((t) => (
                <button
                  key={t.key}
                  className={`compare-subtabs__btn${compareView === t.key ? ' compare-subtabs__btn--active' : ''}`}
                  onClick={() => setCompareView(t.key)}
                  disabled={pickingMode && t.key !== 'split'}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Floating alignment bar */}
            {alignmentResult && !pickingMode && (
              <div className="compare-float-bar compare-float-bar--top">
                <span className={`badge ${alignmentResult.confidence >= 0.7 ? 'badge--success' : 'badge--warning'}`}>
                  {ALIGNMENT_LABELS[alignmentResult.method] || alignmentResult.method}
                </span>
                <span className="compare-float-bar__confidence">
                  {(alignmentResult.confidence * 100).toFixed(0)}%
                </span>
                {onRealign && (
                  <button
                    className="btn btn--sm btn--secondary"
                    onClick={() => {
                      setPickingMode(true);
                      setControlPoints([]);
                      setCurrentPairSide('master');
                      setCompareView('split');
                    }}
                  >
                    Refine
                  </button>
                )}
              </div>
            )}

            {/* Picking mode instruction banner */}
            {pickingMode && (
              <div className="compare-float-bar compare-float-bar--instruction">
                Click matching points: {currentPairSide === 'master' ? 'Original' : 'Changes'} ({completePairs}/4 pairs)
                <button className="btn btn--sm btn--primary" onClick={handleRealign} disabled={completePairs === 0 || loading}>
                  Re-align
                </button>
                <button className="btn btn--sm btn--ghost" onClick={() => { setPickingMode(false); setControlPoints([]); }}>
                  Cancel
                </button>
              </div>
            )}

            {/* Split view */}
            {compareView === 'split' && (
              <div className="compare-split">
                <div className="compare-split__pane">
                  <span className="compare-split__label">
                    Original{pickingMode && currentPairSide === 'master' ? ' — click a point' : ''}
                  </span>
                  <DxfViewerComponent
                    ref={compareOriginalRef}
                    dxfUrl={dxfUrls.original}
                    pickingMode={pickingMode && currentPairSide === 'master'}
                    onPointClick={handleMasterPointClick}
                  />
                  {pickingMode && controlPoints.map((p, i) => p.master && (
                    <div key={`m-${i}`} className="control-point-marker control-point-marker--master" title={`Point ${i + 1}`}>
                      {i + 1}
                    </div>
                  ))}
                </div>
                <div className="compare-split__pane">
                  <span className="compare-split__label">
                    Changes{pickingMode && currentPairSide === 'revision' ? ' — click corresponding point' : ''}
                  </span>
                  <DxfViewerComponent
                    ref={compareChangesRef}
                    dxfUrl={dxfUrls.comparison}
                    pickingMode={pickingMode && currentPairSide === 'revision'}
                    onPointClick={handleRevisionPointClick}
                  />
                  {pickingMode && controlPoints.map((p, i) => p.revision && (
                    <div key={`r-${i}`} className="control-point-marker control-point-marker--revision" title={`Point ${i + 1}`}>
                      {i + 1}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Full-screen Original view */}
            {compareView === 'original' && (
              <DxfViewerComponent dxfUrl={dxfUrls.original} />
            )}

            {/* Full-screen Revised view */}
            {compareView === 'revised' && (
              <DxfViewerComponent dxfUrl={dxfUrls.comparison} />
            )}

            {/* Floating diff summary badges */}
            {comparisonResult && comparisonResult.summary && comparisonResult.total_changes > 0 && (
              <div className="compare-float-bar compare-float-bar--bottom">
                {comparisonResult.summary.added > 0 && (
                  <span className="comparison-badge comparison-badge--added">+{comparisonResult.summary.added} added</span>
                )}
                {comparisonResult.summary.removed > 0 && (
                  <span className="comparison-badge comparison-badge--removed">-{comparisonResult.summary.removed} removed</span>
                )}
                {comparisonResult.summary.modified > 0 && (
                  <span className="comparison-badge comparison-badge--modified">~{comparisonResult.summary.modified} modified</span>
                )}
                {comparisonResult.summary.moved > 0 && (
                  <span className="comparison-badge comparison-badge--moved">&rarr;{comparisonResult.summary.moved} moved</span>
                )}
              </div>
            )}
          </div>
        ) : dxfUrls?.[activeTab] ? (
          <div style={{ transform: `rotate(${rotation}deg)`, transition: 'transform 0.3s', width: '100%', height: '100%' }}>
            <DxfViewerComponent ref={activeViewerRef} dxfUrl={dxfUrls[activeTab]} onEntityClick={onEntityClick} selectedEntities={selectedEntities} />
          </div>
        ) : previewUrls[activeTab] ? (
          <img
            src={previewUrls[activeTab]}
            alt={`${activeTab} drawing preview`}
            loading="lazy"
            style={{ transform: `rotate(${rotation}deg)`, transition: 'transform 0.3s', maxWidth: '100%' }}
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
        <div
          className="resize-handle"
          onPointerDown={handleResizePointerDown}
          onPointerMove={handleResizePointerMove}
          onPointerUp={handleResizePointerUp}
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize viewer and controls"
        />
        <div className="preview__controls" style={controlsStyle}>
          {/* Step 1: Upload — full form if no revision, compact summary if revision loaded */}
          {(!revisionOps || revisionOps.length === 0) && !bundleReady && !alignmentResult && (
            <div className="wizard-step">
              <h4 className="op-list__title">Upload Revision</h4>
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
                      ? 'Geometry only (lines, polylines, arcs, blocks) — excludes text, title blocks, notes, borders, and seal layers'
                      : selectedProfile
                        ? `Filter: ${selectedProfile}`
                        : 'Compare all entities on all layers (recommended for saw cuts and annotation changes)'}
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

          {/* Compact file summary after revision loaded */}
          {(revisionOps?.length > 0 || alignmentResult) && !bundleReady && (
            <div className="wizard-step-compact">
              <input
                ref={revisionInputRef}
                type="file"
                accept=".dxf,.dwg"
                onChange={useWizard ? handleRevisionUpload : handleSimpleCompare}
                style={{ display: 'none' }}
                id="revision-upload-replace"
                aria-label="Replace revision file"
              />
              <span className="wizard-step-compact__file">
                {revisionFile || 'Revision file'}
              </span>
              <button
                className="btn btn--sm btn--ghost"
                onClick={() => revisionInputRef.current?.click()}
                disabled={loading}
              >
                Replace
              </button>
              {diffSummary && (
                <span className="text-xs text-secondary">{diffSummary.headline}</span>
              )}
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
                      data-testid="revision-op-item"
                      aria-label={`${op.op_type} ${op.description}: ${op.status}`}
                      onClick={() => { setFocusedOpIndex(i); handleFocusRevisionOp(op); }}
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
        </div>
        </>
      )}

      {/* ===== STRUCTURED PREVIEW (EPIC-CAD-08) ===== */}
      {editPreview && activeTab !== 'comparison' && (
        <div className="preview__controls">
          <div className="op-list">
            <h4 className="op-list__title">
              Edit Preview
              {editPreview.data?.status === 'blocked' && (
                <span className="comparison-badge comparison-badge--removed" style={{ marginLeft: 'var(--space-2)' }}>Blocked</span>
              )}
            </h4>
            {editPreview.operations?.map((op, i) => (
              <div key={op.action_id || i} className="revision-op-item" data-testid="edit-op-item" style={{ cursor: 'pointer' }} onClick={() => handleFocusEditOp(op)}>
                <div className="revision-op-item__header">
                  <span className={`op-item__type op-item__type--${opTypeClass(op.action_type)}`}>
                    {op.action_type}
                  </span>
                  <span className="revision-op-item__confidence" title="Confidence">
                    {((op.confidence || 1) * 100).toFixed(0)}%
                  </span>
                  {op.is_destructive && (
                    <span className="comparison-badge comparison-badge--removed">destructive</span>
                  )}
                </div>
                <p className="revision-op-item__desc">{op.description}</p>
                {op.before_state && Object.keys(op.before_state).length > 0 && (
                  <div className="text-xs text-secondary">Before: {JSON.stringify(op.before_state)}</div>
                )}
                {op.after_state && Object.keys(op.after_state).length > 0 && (
                  <div className="text-xs text-secondary">After: {JSON.stringify(op.after_state)}</div>
                )}
                {op.warnings?.length > 0 && (
                  <div className="text-xs" style={{ color: 'var(--color-warning)' }}>
                    {op.warnings.join('; ')}
                  </div>
                )}
              </div>
            ))}
          </div>

          {editPreview.data?.status !== 'blocked' && !structuredApplyResult && (
            <div className="flex gap-2" style={{ marginTop: 'var(--space-2)' }}>
              <button
                className="btn btn--primary btn--full"
                onClick={() => onApproveAndApplyPlan?.()}
                disabled={loading}
              >
                {loading ? <span className="spinner" aria-hidden="true" /> : 'Approve & Apply'}
              </button>
              <button
                className="btn btn--ghost"
                onClick={() => onApprovePlan?.(false)}
                disabled={loading}
              >
                Reject
              </button>
            </div>
          )}

          {structuredApplyResult && (
            <div className="bundle-download" style={{ marginTop: 'var(--space-2)' }}>
              <p className="bundle-download__status">
                {structuredApplyResult.data?.status === 'success' ? 'Applied successfully' : `Status: ${structuredApplyResult.data?.status || 'unknown'}`}
                {' '}{structuredApplyResult.data?.success_count || 0} succeeded
                {structuredApplyResult.data?.failure_count > 0 && (
                  <span className="comparison-badge comparison-badge--removed" style={{ marginLeft: 'var(--space-2)' }}>
                    {structuredApplyResult.data.failure_count} failed
                  </span>
                )}
              </p>
              <button
                className="btn btn--secondary btn--full"
                onClick={onDownload}
                disabled={loading}
              >
                Download Edited DXF
              </button>
            </div>
          )}
        </div>
      )}

      {/* ===== EDIT TAB CONTENT ===== */}
      {!editPreview && (hasOperations || hasEdited) && activeTab !== 'comparison' && (
        <div className="preview__controls">
          {hasOperations && (
            <div className="op-list">
              <h4 className="op-list__title">Planned operations</h4>
              {operations.map((op, i) => (
                <label
                  key={i}
                  className="op-item op-item--clickable"
                  onClick={() => op.bounds && activeViewerRef.current?.focusOnBounds(op.bounds)}
                  style={{ cursor: op.bounds ? 'pointer' : 'default' }}
                >
                  <input
                    type="checkbox"
                    className="op-item__checkbox"
                    checked={selectedOps.includes(i)}
                    onChange={() => onToggleOp(i)}
                    onClick={e => e.stopPropagation()}
                  />
                  <span className="op-item__text">{op.description || op.summary || `Operation ${i + 1}`}</span>
                  <span className={`op-item__type op-item__type--${opTypeClass(op.op_type)}`}>
                    {op.op_type}
                  </span>
                </label>
              ))}
            </div>
          )}

          {hasOperations && (
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
