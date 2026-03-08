/**
 * CandidateList — shows ambiguity candidates from the precision planner.
 *
 * Renders when ambiguity_candidates is present and non-empty in the v2 response.
 * Each card shows handle, layer, entity type, and a confidence bar.
 * "Select" re-sends the prompt with that handle as the only target.
 *
 * Usage:
 *   <CandidateList
 *     candidates={ambiguityCandidates}
 *     onSelect={(handle) => sendPromptWithHandle(handle)}
 *   />
 *
 * Props:
 *   candidates — array of { handle, layer, entity_type, confidence, description? }
 *   onSelect   — callback(handle: string) called when user picks a candidate
 */

function ConfidenceBar({ value }) {
  const pct = Math.round((value ?? 0) * 100);
  const color =
    pct >= 80
      ? 'var(--accent-success)'
      : pct >= 50
      ? 'var(--accent-warning)'
      : 'var(--accent-danger)';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
      }}
      title={`Confidence: ${pct}%`}
      aria-label={`Confidence ${pct}%`}
    >
      <div
        style={{
          flex: 1,
          height: 4,
          borderRadius: 2,
          background: 'var(--bg-tertiary)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: color,
            borderRadius: 2,
            transition: 'width var(--transition-base)',
          }}
        />
      </div>
      <span
        style={{
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)',
          color,
          fontWeight: 700,
          minWidth: 32,
          textAlign: 'right',
        }}
      >
        {pct}%
      </span>
    </div>
  );
}

function entityTypeClass(type) {
  if (!type) return 'edit';
  const t = type.toLowerCase();
  if (t === 'line' || t === 'lwpolyline') return 'move';
  if (t === 'text' || t === 'mtext') return 'edit';
  if (t === 'insert') return 'add';
  return 'edit';
}

export default function CandidateList({ candidates, onSelect }) {
  if (!candidates || candidates.length === 0) return null;

  return (
    <div
      style={{
        padding: 'var(--space-3) var(--space-4)',
        borderTop: '1px solid var(--border-default)',
        background: 'var(--bg-secondary)',
      }}
    >
      <h4
        className="op-list__title"
        style={{ marginBottom: 'var(--space-2)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}
      >
        <span
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--accent-warning)',
            flexShrink: 0,
          }}
          aria-hidden="true"
        />
        Ambiguous — select a candidate
        <span
          style={{
            marginLeft: 'auto',
            fontSize: 'var(--text-xs)',
            fontWeight: 400,
            color: 'var(--text-tertiary)',
          }}
        >
          {candidates.length} match{candidates.length !== 1 ? 'es' : ''}
        </span>
      </h4>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          maxHeight: 220,
          overflowY: 'auto',
        }}
        role="list"
        aria-label="Ambiguity candidates"
      >
        {candidates.map((c) => (
          <div
            key={c.handle}
            role="listitem"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-1)',
              padding: 'var(--space-2) var(--space-3)',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 'var(--space-2)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0 }}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-xs)',
                    background: 'var(--bg-tertiary)',
                    padding: '1px 6px',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--text-primary)',
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                  title="Entity handle"
                >
                  {c.handle}
                </span>
                {c.entity_type && (
                  <span
                    className={`op-item__type op-item__type--${entityTypeClass(c.entity_type)}`}
                    style={{ flexShrink: 0 }}
                  >
                    {c.entity_type}
                  </span>
                )}
                {c.layer && (
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-secondary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={`Layer: ${c.layer}`}
                  >
                    {c.layer}
                  </span>
                )}
              </div>
              <button
                type="button"
                className="btn btn--sm btn--secondary"
                onClick={() => onSelect(c.handle)}
                aria-label={`Select entity ${c.handle}`}
                style={{ flexShrink: 0 }}
              >
                Select
              </button>
            </div>

            {c.description && (
              <p
                style={{
                  margin: 0,
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-secondary)',
                  lineHeight: 1.5,
                }}
              >
                {c.description}
              </p>
            )}

            <ConfidenceBar value={c.confidence ?? 0} />
          </div>
        ))}
      </div>
    </div>
  );
}
