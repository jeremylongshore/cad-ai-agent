/**
 * DesignOpsPanel -- renders design operations results (layout recommendations,
 * revision summaries, takeoff candidates, scope summaries) with confidence
 * badges, caveats, and expand/collapse.
 */

import { useState } from 'react';

function ConfidenceBadge({ value, label }) {
  if (value == null && !label) return null;
  const pct = value != null ? Math.round(value * 100) : null;
  const level = pct != null
    ? (pct >= 80 ? 'high' : pct >= 50 ? 'medium' : 'low')
    : (label === 'high' ? 'high' : label === 'medium' ? 'medium' : 'low');
  const text = pct != null ? `${pct}%` : label;
  return (
    <span className={`badge badge--${level === 'high' ? 'success' : level === 'medium' ? 'warning' : ''}`}>
      {text}
    </span>
  );
}

function CaveatList({ caveats }) {
  if (!caveats || caveats.length === 0) return null;
  return (
    <ul className="text-xs text-tertiary" style={{ marginTop: 'var(--space-1)', paddingLeft: 'var(--space-3)' }}>
      {caveats.map((c, i) => <li key={i}>{c}</li>)}
    </ul>
  );
}

function CollapsibleSection({ title, confidence, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ border: '1px solid var(--border-primary)', borderRadius: 'var(--radius-md)', marginBottom: 'var(--space-2)' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: 'var(--space-2) var(--space-3)', background: 'none', border: 'none',
          cursor: 'pointer', color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.875rem',
        }}
      >
        <span>{open ? '\u25BC' : '\u25B6'} {title}</span>
        <ConfidenceBadge value={confidence} />
      </button>
      {open && <div style={{ padding: '0 var(--space-3) var(--space-2)' }}>{children}</div>}
    </div>
  );
}

function RecommendationList({ recommendations }) {
  if (!recommendations || recommendations.length === 0) return <p className="text-sm text-secondary">No recommendations.</p>;
  return (
    <div>
      {recommendations.map((rec, i) => (
        <div key={i} style={{ marginBottom: 'var(--space-2)', paddingBottom: 'var(--space-2)', borderBottom: '1px solid var(--border-secondary)' }}>
          <div className="flex items-center gap-2">
            <span className="badge">{rec.type?.replace(/_/g, ' ')}</span>
            <ConfidenceBadge value={rec.confidence} />
          </div>
          <p className="text-sm" style={{ fontWeight: 600, marginTop: 'var(--space-1)' }}>{rec.title}</p>
          <p className="text-sm text-secondary">{rec.description}</p>
          <CaveatList caveats={rec.caveats} />
        </div>
      ))}
    </div>
  );
}

function TakeoffTable({ items }) {
  if (!items || items.length === 0) return <p className="text-sm text-secondary">No takeoff items.</p>;
  return (
    <table style={{ width: '100%', fontSize: '0.8125rem', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ borderBottom: '2px solid var(--border-primary)' }}>
          <th style={{ textAlign: 'left', padding: 'var(--space-1)' }}>Item</th>
          <th style={{ textAlign: 'right', padding: 'var(--space-1)' }}>Qty</th>
          <th style={{ textAlign: 'left', padding: 'var(--space-1)' }}>Layer</th>
          <th style={{ textAlign: 'center', padding: 'var(--space-1)' }}>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, i) => (
          <tr key={i} style={{ borderBottom: '1px solid var(--border-secondary)' }}>
            <td style={{ padding: 'var(--space-1)' }}>{item.name}</td>
            <td style={{ textAlign: 'right', padding: 'var(--space-1)' }}>{item.quantity}{item.unit ? ` ${item.unit}` : ''}</td>
            <td style={{ padding: 'var(--space-1)' }}>{item.source_layer}</td>
            <td style={{ textAlign: 'center', padding: 'var(--space-1)' }}><ConfidenceBadge label={item.confidence} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ChangeSummaryList({ changes }) {
  if (!changes || changes.length === 0) return <p className="text-sm text-secondary">No changes to summarize.</p>;
  return (
    <ul style={{ listStyle: 'none', padding: 0 }}>
      {changes.map((c, i) => (
        <li key={i} style={{ marginBottom: 'var(--space-1)', paddingBottom: 'var(--space-1)', borderBottom: '1px solid var(--border-secondary)' }}>
          <span className="badge" style={{ marginRight: 'var(--space-1)' }}>{c.change_type}</span>
          <span className="text-sm">{c.plain_description}</span>
          {c.technical_detail && <span className="text-xs text-tertiary"> ({c.technical_detail})</span>}
        </li>
      ))}
    </ul>
  );
}

export default function DesignOpsPanel({ data }) {
  if (!data) return null;

  const taskFamily = data.task_family;
  const payload = data.data || {};

  // Scope summary (has sections array)
  if (payload.sections) {
    return (
      <div className="design-ops-panel">
        <h4 style={{ marginBottom: 'var(--space-2)' }}>{payload.title || 'Design Operations Report'}</h4>
        {payload.omitted_sections?.length > 0 && (
          <p className="text-xs text-tertiary">
            Omitted: {payload.omitted_sections.join(', ')}
          </p>
        )}
        {payload.sections.map((section, i) => (
          <CollapsibleSection key={i} title={section.title} confidence={section.confidence} defaultOpen={i === 0}>
            {section.section_type === 'layout_recommendations' && (
              <RecommendationList recommendations={section.content?.recommendations} />
            )}
            {section.section_type === 'takeoff_candidates' && (
              <TakeoffTable items={section.content?.items} />
            )}
            {section.section_type === 'revision_summary' && (
              <ChangeSummaryList changes={section.content?.key_changes} />
            )}
            {section.section_type === 'general_notes' && (
              <pre className="text-sm">{JSON.stringify(section.content, null, 2)}</pre>
            )}
            <CaveatList caveats={section.caveats} />
          </CollapsibleSection>
        ))}
        <CaveatList caveats={payload.caveats} />
      </div>
    );
  }

  // Layout recommendations
  if (payload.recommendations) {
    return (
      <div className="design-ops-panel">
        <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
          <h4>{payload.total_recommendations} Recommendation(s)</h4>
          <ConfidenceBadge value={payload.aggregate_confidence} />
        </div>
        <p className="text-sm text-secondary">{payload.drawing_summary}</p>
        <RecommendationList recommendations={payload.recommendations} />
        <CaveatList caveats={payload.limitations} />
      </div>
    );
  }

  // Takeoff candidates
  if (payload.items) {
    return (
      <div className="design-ops-panel">
        <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
          <h4>{payload.total_items} Takeoff Item(s)</h4>
          <ConfidenceBadge label={payload.aggregate_confidence} />
        </div>
        <TakeoffTable items={payload.items} />
        {payload.provenance_warnings?.length > 0 && (
          <div className="text-xs text-tertiary" style={{ marginTop: 'var(--space-2)' }}>
            {payload.provenance_warnings.map((w, i) => <p key={i}>{w}</p>)}
          </div>
        )}
        <CaveatList caveats={payload.caveats} />
      </div>
    );
  }

  // Revision summary
  if (payload.key_changes) {
    return (
      <div className="design-ops-panel">
        <h4 style={{ marginBottom: 'var(--space-2)' }}>{payload.headline}</h4>
        <p className="text-sm text-secondary">{payload.overall_assessment}</p>
        <ChangeSummaryList changes={payload.key_changes} />
        <CaveatList caveats={payload.caveats} />
      </div>
    );
  }

  // Fallback: show raw data
  return (
    <div className="design-ops-panel">
      <pre className="text-sm">{JSON.stringify(payload, null, 2)}</pre>
    </div>
  );
}
