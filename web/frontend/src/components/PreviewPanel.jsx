import { useState, useEffect, useRef } from 'react';

const TABS = [
  { key: 'original', label: 'Original' },
  { key: 'edited', label: 'Edited' },
  { key: 'diff', label: 'Diff' },
  { key: 'comparison', label: 'Compare' },
];

export default function PreviewPanel({
  previewUrls,
  operations,
  selectedOps,
  onToggleOp,
  onApply,
  onDownload,
  onCompare,
  comparisonResult,
  loading,
}) {
  const [activeTab, setActiveTab] = useState('original');
  const hasEdited = !!previewUrls.edited;
  const hasOperations = operations.length > 0;
  const hasComparison = !!previewUrls.comparison;
  const revisionInputRef = useRef(null);

  useEffect(() => {
    if (previewUrls.edited) setActiveTab('edited');
  }, [previewUrls.edited]);

  useEffect(() => {
    if (previewUrls.comparison) setActiveTab('comparison');
  }, [previewUrls.comparison]);

  const handleRevisionUpload = (e) => {
    const file = e.target.files?.[0];
    if (file && onCompare) {
      onCompare(file);
    }
    // Reset input so re-uploading same file triggers change
    if (revisionInputRef.current) revisionInputRef.current.value = '';
  };

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
        {previewUrls[activeTab] ? (
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
                ? 'Upload a revision DXF to compare against the original'
                : 'Run an edit to see the result'}
          </div>
        )}
      </div>

      {/* Comparison summary */}
      {activeTab === 'comparison' && comparisonResult && (
        <div className="comparison-summary">
          <h4 className="op-list__title">Comparison Results</h4>
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

      {/* Upload revision button (always visible when file loaded) */}
      {activeTab === 'comparison' && onCompare && (
        <div style={{ marginTop: 'var(--space-2)' }}>
          <input
            ref={revisionInputRef}
            type="file"
            accept=".dxf"
            onChange={handleRevisionUpload}
            style={{ display: 'none' }}
            id="revision-upload"
          />
          <button
            className="btn btn--secondary btn--full"
            onClick={() => revisionInputRef.current?.click()}
            disabled={loading}
          >
            {loading ? <span className="spinner" aria-hidden="true" /> : 'Upload Revision DXF'}
          </button>
        </div>
      )}

      {hasOperations && (
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
              <span className={`op-item__type op-item__type--${typeClass(op.op_type)}`}>
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
  );
}

function typeClass(opType) {
  if (!opType) return 'edit';
  const t = opType.toLowerCase();
  if (t.includes('move')) return 'move';
  if (t.includes('delete')) return 'delete';
  if (t.includes('add')) return 'add';
  return 'edit';
}
