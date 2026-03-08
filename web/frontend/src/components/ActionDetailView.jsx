import { useState } from 'react';

/**
 * ActionDetailView — expandable per-operation breakdown for EPIC-CAD-14.
 *
 * Shows the full detail of each precision action including before/after state,
 * status badge, skip reason, confidence, and evidence list.
 *
 * Usage:
 *   <ActionDetailView actions={precisionActions} />
 *
 * Props:
 *   actions — array of action detail objects:
 *     {
 *       action_id?: string,
 *       handle: string,
 *       entity_type?: string,
 *       layer?: string,
 *       action_type: string,
 *       status: 'planned' | 'applied' | 'skipped' | 'blocked',
 *       description?: string,
 *       before_state?: Record<string, unknown>,
 *       after_state?: Record<string, unknown>,
 *       skip_reason?: string,
 *       confidence?: number,
 *       evidence?: string[],
 *     }
 */

const STATUS_COLORS = {
  planned: 'var(--accent-primary)',
  applied: 'var(--accent-success)',
  skipped: 'var(--text-tertiary)',
  blocked: 'var(--accent-danger)',
};

const STATUS_BG = {
  planned: 'var(--accent-primary-light)',
  applied: 'var(--accent-success-light)',
  skipped: 'var(--bg-tertiary)',
  blocked: 'var(--accent-danger-light)',
};

function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] ?? 'var(--text-secondary)';
  const bg = STATUS_BG[status] ?? 'var(--bg-tertiary)';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 8px',
        borderRadius: 'var(--radius-full)',
        fontSize: 'var(--text-xs)',
        fontWeight: 600,
        color,
        background: bg,
        border: `1px solid ${color}`,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        flexShrink: 0,
      }}
      aria-label={`Status: ${status}`}
    >
      {status}
    </span>
  );
}

function KVTable({ data, label }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <div style={{ marginTop: 'var(--space-1)' }}>
      <span
        style={{
          fontSize: 'var(--text-xs)',
          fontWeight: 600,
          color: 'var(--text-tertiary)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}
      >
        {label}
      </span>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          marginTop: 4,
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        <tbody>
          {entries.map(([key, val]) => (
            <tr key={key}>
              <td
                style={{
                  padding: '2px 8px 2px 0',
                  color: 'var(--text-tertiary)',
                  verticalAlign: 'top',
                  whiteSpace: 'nowrap',
                }}
              >
                {key}
              </td>
              <td
                style={{
                  padding: '2px 0',
                  color: 'var(--text-primary)',
                  wordBreak: 'break-all',
                }}
              >
                {typeof val === 'object' ? JSON.stringify(val) : String(val)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfidenceIndicator({ value }) {
  const pct = Math.round((value ?? 1) * 100);
  const color =
    pct >= 80
      ? 'var(--accent-success)'
      : pct >= 50
      ? 'var(--accent-warning)'
      : 'var(--accent-danger)';
  return (
    <span
      style={{
        fontSize: 'var(--text-xs)',
        fontFamily: 'var(--font-mono)',
        color,
        fontWeight: 700,
      }}
      title={`Confidence: ${pct}%`}
    >
      {pct}%
    </span>
  );
}

function ActionCard({ action, index }) {
  const [expanded, setExpanded] = useState(false);

  const hasDetails =
    (action.before_state && Object.keys(action.before_state).length > 0) ||
    (action.after_state && Object.keys(action.after_state).length > 0) ||
    action.skip_reason ||
    (action.evidence && action.evidence.length > 0);

  return (
    <div
      style={{
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-primary)',
        overflow: 'hidden',
      }}
    >
      {/* Card header — always visible */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 'var(--space-2)',
          padding: 'var(--space-2) var(--space-3)',
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
            flexShrink: 0,
            paddingTop: 1,
          }}
        >
          {index + 1}
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 'var(--space-1)',
              marginBottom: 'var(--space-1)',
            }}
          >
            {/* Action type badge */}
            <span
              className={`op-item__type op-item__type--${actionTypeClass(action.action_type)}`}
            >
              {action.action_type}
            </span>

            {/* Handle */}
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                background: 'var(--bg-tertiary)',
                padding: '1px 6px',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                fontWeight: 600,
              }}
              title="Entity handle"
            >
              {action.handle}
            </span>

            {action.entity_type && (
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-tertiary)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {action.entity_type}
              </span>
            )}

            {action.layer && (
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-secondary)',
                }}
                title={`Layer: ${action.layer}`}
              >
                @{action.layer}
              </span>
            )}

            <StatusBadge status={action.status ?? 'planned'} />

            {action.confidence != null && (
              <ConfidenceIndicator value={action.confidence} />
            )}
          </div>

          {action.description && (
            <p
              style={{
                margin: 0,
                fontSize: 'var(--text-xs)',
                color: 'var(--text-secondary)',
                lineHeight: 1.5,
              }}
            >
              {action.description}
            </p>
          )}
        </div>

        {hasDetails && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            style={{ flexShrink: 0, padding: '2px 6px' }}
          >
            {expanded ? 'Less' : 'More'}
          </button>
        )}
      </div>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div
          style={{
            borderTop: '1px solid var(--border-default)',
            padding: 'var(--space-2) var(--space-3)',
            background: 'var(--bg-secondary)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
          }}
        >
          {action.before_state && Object.keys(action.before_state).length > 0 && (
            <KVTable data={action.before_state} label="Before" />
          )}
          {action.after_state && Object.keys(action.after_state).length > 0 && (
            <KVTable data={action.after_state} label="After" />
          )}
          {action.skip_reason && (
            <div>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  color: 'var(--text-tertiary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                Skip reason
              </span>
              <p
                style={{
                  margin: '4px 0 0',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--accent-warning)',
                  fontStyle: 'italic',
                }}
              >
                {action.skip_reason}
              </p>
            </div>
          )}
          {action.evidence && action.evidence.length > 0 && (
            <div>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  color: 'var(--text-tertiary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                Evidence
              </span>
              <ul
                style={{
                  margin: '4px 0 0',
                  paddingLeft: 'var(--space-4)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-secondary)',
                  lineHeight: 1.6,
                }}
              >
                {action.evidence.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ActionDetailView({ actions }) {
  if (!actions || actions.length === 0) return null;

  const counts = actions.reduce((acc, a) => {
    const s = a.status ?? 'planned';
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div
      style={{
        padding: 'var(--space-3) var(--space-4)',
        borderTop: '1px solid var(--border-default)',
        background: 'var(--bg-secondary)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 'var(--space-2)',
        }}
      >
        <h4 className="op-list__title" style={{ margin: 0 }}>
          Precision Actions
        </h4>
        <div style={{ display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap' }}>
          {Object.entries(counts).map(([status, count]) => (
            <span
              key={status}
              style={{
                fontSize: 'var(--text-xs)',
                padding: '1px 6px',
                borderRadius: 'var(--radius-full)',
                background: STATUS_BG[status] ?? 'var(--bg-tertiary)',
                color: STATUS_COLORS[status] ?? 'var(--text-secondary)',
                fontWeight: 600,
              }}
            >
              {count} {status}
            </span>
          ))}
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          maxHeight: 320,
          overflowY: 'auto',
        }}
        role="list"
        aria-label="Precision action details"
      >
        {actions.map((action, i) => (
          <ActionCard key={action.action_id ?? i} action={action} index={i} />
        ))}
      </div>
    </div>
  );
}

function actionTypeClass(actionType) {
  if (!actionType) return 'edit';
  const t = actionType.toLowerCase();
  if (t.includes('move')) return 'move';
  if (t.includes('delete') || t.includes('remove')) return 'delete';
  if (t.includes('add')) return 'add';
  return 'edit';
}
