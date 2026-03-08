import { useState, useCallback } from 'react';

/**
 * PrecisionPanel — collapsible precision controls for EPIC-CAD-14.
 *
 * Usage:
 *   <PrecisionPanel
 *     controls={precisionControls}
 *     onChange={setPrecisionControls}
 *     fileInfo={fileInfo}
 *   />
 *
 * onChange receives a client_metadata object:
 *   {
 *     precision: {
 *       target_handles: string[],
 *       target_layers: string[],
 *       exclude_layers: string[],
 *       target_types: string[],
 *       model_space_only: boolean,
 *       exact_delta: { dx: number, dy: number } | null,
 *       confidence_threshold: number,
 *       disable_inference: boolean,
 *     }
 *   }
 * or null when all fields are at defaults (cleared).
 */

const ENTITY_TYPES = ['LINE', 'LWPOLYLINE', 'TEXT', 'MTEXT', 'INSERT', 'CIRCLE', 'ARC'];

const EMPTY = {
  target_handles: '',
  target_layers: [],
  exclude_layers: '',
  target_types: [],
  model_space_only: false,
  dx: '',
  dy: '',
  confidence_threshold: 0.5,
  disable_inference: false,
};

function hasAnyValue(local) {
  return (
    local.target_handles.trim() !== '' ||
    local.target_layers.length > 0 ||
    local.exclude_layers.trim() !== '' ||
    local.target_types.length > 0 ||
    local.model_space_only ||
    local.dx !== '' ||
    local.dy !== '' ||
    local.confidence_threshold !== 0.5 ||
    local.disable_inference
  );
}

function toMetadata(local) {
  if (!hasAnyValue(local)) return null;

  const precision = {
    confidence_threshold: local.confidence_threshold,
    model_space_only: local.model_space_only,
    disable_inference: local.disable_inference,
  };

  const handles = local.target_handles
    .split(',')
    .map((h) => h.trim())
    .filter(Boolean);
  if (handles.length > 0) precision.target_handles = handles;

  if (local.target_layers.length > 0) precision.target_layers = local.target_layers;

  const excLayers = local.exclude_layers
    .split(',')
    .map((l) => l.trim())
    .filter(Boolean);
  if (excLayers.length > 0) precision.exclude_layers = excLayers;

  if (local.target_types.length > 0) precision.target_types = local.target_types;

  const dx = parseFloat(local.dx);
  const dy = parseFloat(local.dy);
  if (!isNaN(dx) || !isNaN(dy)) {
    precision.exact_delta = { dx: isNaN(dx) ? 0 : dx, dy: isNaN(dy) ? 0 : dy };
  }

  return { precision };
}

export default function PrecisionPanel({ controls, onChange, fileInfo }) {
  const [open, setOpen] = useState(false);
  const [local, setLocal] = useState(EMPTY);

  const update = useCallback((patch) => {
    setLocal((prev) => {
      const next = { ...prev, ...patch };
      onChange(toMetadata(next));
      return next;
    });
  }, [onChange]);

  const clearAll = useCallback(() => {
    setLocal(EMPTY);
    onChange(null);
  }, [onChange]);

  const toggleType = useCallback((type) => {
    setLocal((prev) => {
      const next = prev.target_types.includes(type)
        ? { ...prev, target_types: prev.target_types.filter((t) => t !== type) }
        : { ...prev, target_types: [...prev.target_types, type] };
      onChange(toMetadata(next));
      return next;
    });
  }, [onChange]);

  const toggleLayer = useCallback((layer) => {
    setLocal((prev) => {
      const next = prev.target_layers.includes(layer)
        ? { ...prev, target_layers: prev.target_layers.filter((l) => l !== layer) }
        : { ...prev, target_layers: [...prev.target_layers, layer] };
      onChange(toMetadata(next));
      return next;
    });
  }, [onChange]);

  const availableLayers = fileInfo?.layers ?? [];
  const isActive = controls !== null;

  return (
    <div
      className="precision-panel"
      style={{
        borderTop: '1px solid var(--border-default)',
        background: 'var(--bg-secondary)',
      }}
    >
      {/* Header / toggle */}
      <button
        type="button"
        className="precision-panel__toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="precision-panel-body"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
          padding: 'var(--space-2) var(--space-4)',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
          fontSize: 'var(--text-xs)',
          fontWeight: 600,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
        }}
      >
        <span>
          Precision Controls
          {isActive && (
            <span
              style={{
                marginLeft: 'var(--space-2)',
                background: 'var(--accent-primary)',
                color: 'white',
                borderRadius: 'var(--radius-full)',
                padding: '1px 6px',
                fontSize: '0.65rem',
                fontWeight: 700,
                verticalAlign: 'middle',
              }}
            >
              active
            </span>
          )}
        </span>
        <span
          aria-hidden="true"
          style={{
            transition: 'transform var(--transition-fast)',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            display: 'inline-block',
          }}
        >
          &#9660;
        </span>
      </button>

      {/* Collapsible body */}
      {open && (
        <div
          id="precision-panel-body"
          style={{
            padding: 'var(--space-3) var(--space-4) var(--space-4)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)',
          }}
        >
          {/* Target handles */}
          <div className="input-group">
            <label className="input-group__label" htmlFor="pc-handles">
              Target Handles
            </label>
            <input
              id="pc-handles"
              type="text"
              className="input-group__field"
              placeholder="e.g. A1, B2, C3"
              value={local.target_handles}
              onChange={(e) => update({ target_handles: e.target.value })}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
            />
            <span className="input-group__hint" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
              Comma-separated entity handles to restrict operations to
            </span>
          </div>

          {/* Target layers — checkboxes if layers available, text input otherwise */}
          <div className="input-group">
            <span className="input-group__label">Target Layers</span>
            {availableLayers.length > 0 ? (
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 'var(--space-1)',
                  maxHeight: 80,
                  overflowY: 'auto',
                  padding: 'var(--space-1)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--bg-primary)',
                }}
              >
                {availableLayers.map((layer) => (
                  <label
                    key={layer}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: 'var(--text-xs)',
                      cursor: 'pointer',
                      padding: '2px 6px',
                      borderRadius: 'var(--radius-sm)',
                      background: local.target_layers.includes(layer)
                        ? 'var(--accent-primary-light)'
                        : 'transparent',
                      color: local.target_layers.includes(layer)
                        ? 'var(--accent-primary)'
                        : 'var(--text-secondary)',
                      border: local.target_layers.includes(layer)
                        ? '1px solid var(--accent-primary)'
                        : '1px solid transparent',
                      transition: 'all var(--transition-fast)',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={local.target_layers.includes(layer)}
                      onChange={() => toggleLayer(layer)}
                      style={{ width: 12, height: 12 }}
                    />
                    {layer}
                  </label>
                ))}
              </div>
            ) : (
              <input
                type="text"
                className="input-group__field"
                placeholder="e.g. WALLS, COLUMNS"
                value={local.target_layers.join(', ')}
                onChange={(e) =>
                  update({
                    target_layers: e.target.value
                      .split(',')
                      .map((l) => l.trim())
                      .filter(Boolean),
                  })
                }
                style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
              />
            )}
          </div>

          {/* Exclude layers */}
          <div className="input-group">
            <label className="input-group__label" htmlFor="pc-exclude-layers">
              Exclude Layers
            </label>
            <input
              id="pc-exclude-layers"
              type="text"
              className="input-group__field"
              placeholder="e.g. TITLE, NOTES"
              value={local.exclude_layers}
              onChange={(e) => update({ exclude_layers: e.target.value })}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
            />
          </div>

          {/* Entity type filter */}
          <div className="input-group">
            <span className="input-group__label">Entity Types</span>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 'var(--space-1)',
              }}
            >
              {ENTITY_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => toggleType(type)}
                  style={{
                    padding: '2px 8px',
                    fontSize: 'var(--text-xs)',
                    fontFamily: 'var(--font-mono)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                    border: '1px solid',
                    borderColor: local.target_types.includes(type)
                      ? 'var(--accent-primary)'
                      : 'var(--border-default)',
                    background: local.target_types.includes(type)
                      ? 'var(--accent-primary)'
                      : 'var(--bg-primary)',
                    color: local.target_types.includes(type) ? 'white' : 'var(--text-secondary)',
                    transition: 'all var(--transition-fast)',
                  }}
                  aria-pressed={local.target_types.includes(type)}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Model-space only */}
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              cursor: 'pointer',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-primary)',
            }}
          >
            <input
              type="checkbox"
              checked={local.model_space_only}
              onChange={(e) => update({ model_space_only: e.target.checked })}
            />
            Model space only
          </label>

          {/* Exact delta */}
          <div>
            <span
              className="input-group__label"
              style={{ display: 'block', marginBottom: 'var(--space-1)' }}
            >
              Exact Delta
            </span>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <div className="input-group" style={{ flex: 1 }}>
                <label className="input-group__label" htmlFor="pc-dx" style={{ fontSize: 'var(--text-xs)' }}>
                  dx
                </label>
                <input
                  id="pc-dx"
                  type="number"
                  className="input-group__field"
                  placeholder="0"
                  value={local.dx}
                  onChange={(e) => update({ dx: e.target.value })}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
                />
              </div>
              <div className="input-group" style={{ flex: 1 }}>
                <label className="input-group__label" htmlFor="pc-dy" style={{ fontSize: 'var(--text-xs)' }}>
                  dy
                </label>
                <input
                  id="pc-dy"
                  type="number"
                  className="input-group__field"
                  placeholder="0"
                  value={local.dy}
                  onChange={(e) => update({ dy: e.target.value })}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
                />
              </div>
            </div>
          </div>

          {/* Confidence threshold */}
          <div className="input-group">
            <label
              className="input-group__label"
              htmlFor="pc-confidence"
              style={{ display: 'flex', justifyContent: 'space-between' }}
            >
              <span>Confidence Threshold</span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--accent-primary)',
                  fontWeight: 700,
                }}
              >
                {local.confidence_threshold.toFixed(2)}
              </span>
            </label>
            <input
              id="pc-confidence"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={local.confidence_threshold}
              onChange={(e) => update({ confidence_threshold: parseFloat(e.target.value) })}
              style={{ width: '100%', accentColor: 'var(--accent-primary)' }}
            />
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
              }}
            >
              <span>0 — accept all</span>
              <span>1 — exact match only</span>
            </div>
          </div>

          {/* Disable inference */}
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              cursor: 'pointer',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-primary)',
            }}
          >
            <input
              type="checkbox"
              checked={local.disable_inference}
              onChange={(e) => update({ disable_inference: e.target.checked })}
            />
            Disable inference (handle-only targeting)
          </label>

          {/* Clear All */}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={clearAll}
              disabled={!isActive}
            >
              Clear All
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
