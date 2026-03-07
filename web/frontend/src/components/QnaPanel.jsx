/**
 * QnaPanel — renders structured Q&A answers with evidence, confidence, and ambiguity.
 *
 * Displays answer_only, needs_clarification, and unsupported states.
 * Evidence list shows entity handles, layers, and locations.
 */

import { useState, useCallback } from 'react';

function ConfidenceBadge({ confidence }) {
  if (confidence == null) return null;
  const pct = Math.round(confidence * 100);
  const level = pct >= 80 ? 'high' : pct >= 50 ? 'medium' : 'low';
  return (
    <span className={`qna-confidence qna-confidence--${level}`} title="Answer confidence">
      {pct}% confidence
    </span>
  );
}

function EvidenceList({ evidence }) {
  const [expanded, setExpanded] = useState(false);
  if (!evidence || evidence.length === 0) return null;

  const shown = expanded ? evidence : evidence.slice(0, 5);
  const hasMore = evidence.length > 5;

  return (
    <div className="qna-evidence">
      <button
        type="button"
        className="qna-evidence__toggle"
        onClick={() => setExpanded((v) => !v)}
      >
        {evidence.length} evidence item{evidence.length !== 1 ? 's' : ''}
        {hasMore && (expanded ? ' (collapse)' : ' (show all)')}
      </button>
      <ul className="qna-evidence__list">
        {shown.map((ev, i) => (
          <li key={ev.entity_handle || i} className="qna-evidence__item">
            {ev.entity_type && <span className="qna-evidence__type">{ev.entity_type}</span>}
            {ev.layer && <span className="qna-evidence__layer">{ev.layer}</span>}
            {ev.text_excerpt && (
              <span className="qna-evidence__text">"{ev.text_excerpt}"</span>
            )}
            {ev.location && (
              <span className="qna-evidence__loc">
                ({ev.location[0].toFixed(0)}, {ev.location[1].toFixed(0)})
              </span>
            )}
            {ev.entity_handle && (
              <span className="qna-evidence__handle">[{ev.entity_handle}]</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AmbiguityFlags({ flags }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div className="qna-ambiguity">
      {flags.map((flag) => (
        <span key={flag} className="qna-ambiguity__flag">
          {flag.replace(/_/g, ' ')}
        </span>
      ))}
    </div>
  );
}

export default function QnaPanel({ data }) {
  if (!data) return null;

  const {
    message,
    response_type,
    evidence,
    confidence,
    ambiguity_flags,
    data: qnaData,
  } = data;

  const questionType = qnaData?.question_type;
  const entityCount = qnaData?.entity_count;

  // needs_clarification state
  if (response_type === 'needs_clarification') {
    return (
      <div className="qna-panel qna-panel--clarification">
        <p className="qna-panel__message">{message}</p>
      </div>
    );
  }

  // unsupported state
  if (response_type === 'unsupported_operation') {
    return (
      <div className="qna-panel qna-panel--unsupported">
        <p className="qna-panel__message">{message}</p>
      </div>
    );
  }

  // answer_only state
  return (
    <div className="qna-panel qna-panel--answer">
      <div className="qna-panel__header">
        {questionType && (
          <span className="qna-panel__type">
            {questionType.replace(/_/g, ' ')}
          </span>
        )}
        <ConfidenceBadge confidence={confidence} />
        {entityCount != null && entityCount > 0 && (
          <span className="qna-panel__count">{entityCount} entity(ies)</span>
        )}
      </div>
      <pre className="qna-panel__message">{message}</pre>
      <EvidenceList evidence={evidence} />
      <AmbiguityFlags flags={ambiguity_flags} />
    </div>
  );
}
