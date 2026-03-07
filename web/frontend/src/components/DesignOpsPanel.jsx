/**
 * DesignOpsPanel -- renders design and construction operations results (layout
 * recommendations, revision summaries, takeoff candidates, scope summaries,
 * grid analysis, redline reports, batch conditions, field summaries) with
 * confidence badges, caveats, and expand/collapse.
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

function GridTable({ gridLines, bays }) {
  return (
    <div>
      {gridLines && gridLines.length > 0 && (
        <table style={{ width: '100%', fontSize: '0.8125rem', borderCollapse: 'collapse', marginBottom: 'var(--space-2)' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border-primary)' }}>
              <th style={{ textAlign: 'left', padding: 'var(--space-1)' }}>Label</th>
              <th style={{ textAlign: 'left', padding: 'var(--space-1)' }}>Direction</th>
              <th style={{ textAlign: 'right', padding: 'var(--space-1)' }}>Position</th>
              <th style={{ textAlign: 'center', padding: 'var(--space-1)' }}>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {gridLines.map((gl, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border-secondary)' }}>
                <td style={{ padding: 'var(--space-1)' }}>{gl.label || '(unlabeled)'}</td>
                <td style={{ padding: 'var(--space-1)' }}>{gl.direction}</td>
                <td style={{ textAlign: 'right', padding: 'var(--space-1)' }}>{gl.position?.toFixed(1)}</td>
                <td style={{ textAlign: 'center', padding: 'var(--space-1)' }}><ConfidenceBadge value={gl.confidence} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {bays && bays.length > 0 && (
        <>
          <p className="text-sm" style={{ fontWeight: 600, marginBottom: 'var(--space-1)' }}>Bays</p>
          <table style={{ width: '100%', fontSize: '0.8125rem', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-primary)' }}>
                <th style={{ textAlign: 'left', padding: 'var(--space-1)' }}>Bay</th>
                <th style={{ textAlign: 'left', padding: 'var(--space-1)' }}>Direction</th>
                <th style={{ textAlign: 'right', padding: 'var(--space-1)' }}>Dimension</th>
              </tr>
            </thead>
            <tbody>
              {bays.map((bay, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border-secondary)' }}>
                  <td style={{ padding: 'var(--space-1)' }}>{bay.label}</td>
                  <td style={{ padding: 'var(--space-1)' }}>{bay.direction}</td>
                  <td style={{ textAlign: 'right', padding: 'var(--space-1)' }}>{bay.dimension?.toFixed(1)} {bay.unit || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function RedlineList({ entries }) {
  if (!entries || entries.length === 0) return <p className="text-sm text-secondary">No revision clouds found.</p>;
  return (
    <div>
      {entries.map((entry, i) => (
        <div key={i} style={{ marginBottom: 'var(--space-2)', paddingBottom: 'var(--space-2)', borderBottom: '1px solid var(--border-secondary)' }}>
          <div className="flex items-center gap-2">
            <span className="badge">cloud</span>
            <span className="text-sm" style={{ fontWeight: 600 }}>{entry.cloud?.layer}</span>
            <ConfidenceBadge value={entry.confidence} />
          </div>
          <p className="text-sm text-secondary">{entry.description}</p>
          <p className="text-xs text-tertiary">{entry.entity_count} affected entity(ies) on {entry.affected_layers?.join(', ')}</p>
          <CaveatList caveats={entry.caveats} />
        </div>
      ))}
    </div>
  );
}

function ConditionGroupList({ groups }) {
  if (!groups || groups.length === 0) return <p className="text-sm text-secondary">No repeated conditions found.</p>;
  return (
    <div>
      {groups.map((group, i) => (
        <div key={i} style={{ marginBottom: 'var(--space-2)', paddingBottom: 'var(--space-2)', borderBottom: '1px solid var(--border-secondary)' }}>
          <div className="flex items-center gap-2">
            <span className="text-sm" style={{ fontWeight: 600 }}>{group.name}</span>
            <span className="badge">{group.total_instances} instances</span>
            <ConfidenceBadge value={group.confidence} />
          </div>
          <CaveatList caveats={group.caveats} />
        </div>
      ))}
    </div>
  );
}

function renderSection(section) {
  const st = section.section_type;
  // Design-ops section types (EPIC-09)
  if (st === 'layout_recommendations' || st === 'layout_notes') {
    return <RecommendationList recommendations={section.content?.recommendations} />;
  }
  if (st === 'takeoff_candidates' || st === 'takeoff_summary') {
    return <TakeoffTable items={section.content?.items} />;
  }
  if (st === 'revision_summary' || st === 'revision_changes') {
    return <ChangeSummaryList changes={section.content?.key_changes} />;
  }
  // Construction-ops section types (EPIC-10)
  if (st === 'grid_summary') {
    return <GridTable gridLines={section.content?.grid_lines} bays={section.content?.bays} />;
  }
  if (st === 'condition_report') {
    return <ConditionGroupList groups={section.content?.groups} />;
  }
  if (st === 'general_notes') {
    return <pre className="text-sm">{JSON.stringify(section.content, null, 2)}</pre>;
  }
  return <pre className="text-sm">{JSON.stringify(section.content, null, 2)}</pre>;
}

export default function DesignOpsPanel({ data }) {
  if (!data) return null;

  const taskFamily = data.task_family;
  const payload = data.data || {};

  // Scope / field summary (has sections array)
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
            {renderSection(section)}
            <CaveatList caveats={section.caveats} />
          </CollapsibleSection>
        ))}
        <CaveatList caveats={payload.caveats} />
      </div>
    );
  }

  // Grid analysis (standalone)
  if (payload.grid_lines) {
    return (
      <div className="design-ops-panel">
        <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
          <h4>Grid Analysis</h4>
          <ConfidenceBadge value={payload.aggregate_confidence} />
        </div>
        <p className="text-sm text-secondary">{payload.drawing_summary}</p>
        <p className="text-xs text-tertiary">{payload.grid_pattern_description}</p>
        <GridTable gridLines={payload.grid_lines} bays={payload.bays} />
        <CaveatList caveats={payload.caveats} />
      </div>
    );
  }

  // Redline report (standalone)
  if (payload.entries && payload.total_clouds != null) {
    return (
      <div className="design-ops-panel">
        <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
          <h4>{payload.total_clouds} Revision Cloud(s)</h4>
          <ConfidenceBadge value={payload.aggregate_confidence} />
        </div>
        <p className="text-sm text-secondary">{payload.total_affected_entities} affected entity(ies)</p>
        <RedlineList entries={payload.entries} />
        <CaveatList caveats={payload.caveats} />
      </div>
    );
  }

  // Batch condition groups (standalone)
  if (payload.groups) {
    return (
      <div className="design-ops-panel">
        <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
          <h4>{payload.total_groups} Condition Group(s)</h4>
          <ConfidenceBadge value={payload.aggregate_confidence} />
        </div>
        <p className="text-sm text-secondary">{payload.total_instances} total instance(s)</p>
        <ConditionGroupList groups={payload.groups} />
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
