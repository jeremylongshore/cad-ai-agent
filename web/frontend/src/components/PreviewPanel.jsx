import { useState, useEffect } from 'react';

const TABS = [
  { key: 'original', label: 'Original' },
  { key: 'edited', label: 'Edited' },
  { key: 'diff', label: 'Diff' },
];

export default function PreviewPanel({ previewUrls, operations, selectedOps, onToggleOp, onApply, onDownload, loading }) {
  const [activeTab, setActiveTab] = useState('original');
  const hasEdited = !!previewUrls.edited;
  const hasOperations = operations.length > 0;

  useEffect(() => {
    if (previewUrls.edited) setActiveTab('edited');
  }, [previewUrls.edited]);

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
              : 'Run an edit to see the result'}
          </div>
        )}
      </div>

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
