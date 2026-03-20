import { useState, useRef, useEffect, useCallback } from 'react';
import QnaPanel from './QnaPanel';
import DesignOpsPanel from './DesignOpsPanel';

const SUGGESTIONS = [
  'Move column A1 24 feet east',
  'What is on layer NOTES?',
  'How many entities are there?',
  'Add a column mark at grid B3',
];

/** Phased text shown during LLM wait */
const LOADING_PHASES = [
  { after: 0, text: 'Analyzing drawing...' },
  { after: 5, text: 'Planning operations...' },
  { after: 15, text: 'Generating changeset...' },
  { after: 30, text: 'Still working (complex edit)...' },
  { after: 60, text: 'Almost there...' },
];

function getLoadingPhase(elapsedSec) {
  let phase = LOADING_PHASES[0].text;
  for (const p of LOADING_PHASES) {
    if (elapsedSec >= p.after) phase = p.text;
  }
  return phase;
}

/** Context-aware follow-up suggestions based on last message state */
function getFollowUps(messages, hasOperations, hasEdited) {
  if (messages.length === 0) return [];
  const last = messages[messages.length - 1];
  if (!last) return [];

  // After apply
  if (last.role === 'system' && /applied/i.test(last.text)) {
    const chips = ['Download edited DXF'];
    if (hasEdited) chips.push('Make another edit');
    return chips;
  }

  // After error
  if (last.role === 'error') {
    return ['Try a different edit', 'Be more specific'];
  }

  // After AI plan with operations
  if (last.role === 'ai' && hasOperations) {
    return ['Apply all changes', 'Modify the plan'];
  }

  // After AI response with no ops
  if (last.role === 'ai' && !hasOperations) {
    return ['Try being more specific', 'List available entities'];
  }

  return [];
}

function ProgressIndicator({ startTime }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 500);
    return () => clearInterval(interval);
  }, [startTime]);

  return (
    <div className="loading-indicator">
      <span className="spinner" aria-hidden="true" />
      <div className="loading-indicator__text">
        <span className="loading-indicator__phase">{getLoadingPhase(elapsed)}</span>
        <span className="loading-indicator__elapsed">{elapsed}s</span>
      </div>
    </div>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard API may fail in insecure contexts */ }
  }, [text]);

  return (
    <button
      type="button"
      className={`message-actions__btn${copied ? ' message-actions__btn--copied' : ''}`}
      onClick={handleCopy}
      aria-label="Copy message"
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export default function ChatPanel({
  messages,
  onSend,
  onClear,
  onRetry,
  loading,
  loadingStartTime,
  disabled,
  hasOperations,
  hasEdited,
  selectedEntities,
  onRemoveEntity,
  onClearSelection,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const textareaRef = useRef(null);
  const isNearBottomRef = useRef(true);

  // Smart auto-scroll: only scroll if user is near bottom (L5)
  const checkNearBottom = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const threshold = 80;
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  useEffect(() => {
    if (isNearBottomRef.current) {
      // Defer scroll until after React commits the DOM update
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      });
    }
  }, [messages, loading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading || disabled) return;

    if (selectedEntities?.length > 0) {
      const regions = [{ handles: selectedEntities.map(ent => ent.handle) }];
      onSend(trimmed, regions);
      onClearSelection?.();
    } else {
      onSend(trimmed);
    }
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e) => {
    // Enter sends, Shift+Enter newline
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
    // Escape clears input and blurs (M2)
    if (e.key === 'Escape') {
      setInput('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.blur();
      }
    }
  };

  const handleInput = (e) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  const handleExport = useCallback(async () => {
    const lines = messages.map((m) => {
      const label = m.role === 'user' ? 'You' : m.role === 'ai' ? 'AI' : m.role.toUpperCase();
      return `[${label}] ${m.text}`;
    });
    try {
      await navigator.clipboard.writeText(lines.join('\n\n'));
    } catch { /* clipboard may fail */ }
  }, [messages]);

  const followUps = !loading ? getFollowUps(messages, hasOperations, hasEdited) : [];

  return (
    <div className="chat">
      {messages.length > 0 && onClear && (
        <div className="chat__toolbar">
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={handleExport}
            disabled={loading}
          >
            Export
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={onClear}
            disabled={loading}
          >
            Clear chat
          </button>
        </div>
      )}
      <div
        className="chat__messages"
        role="log"
        aria-label="Chat messages"
        ref={messagesContainerRef}
        onScroll={checkNearBottom}
      >
        {messages.length === 0 ? (
          <div className="chat__empty">
            <p className="chat__empty-title">Ask a question or describe an edit</p>
            <p className="chat__empty-text">
              I can answer questions about your drawing, list entities, search text, and plan edits.
            </p>
            {!disabled && (
              <div className="chat__suggestions">
                {SUGGESTIONS.map((text) => (
                  <button
                    key={text}
                    type="button"
                    className="chat__suggestion"
                    onClick={() => setInput(text)}
                  >
                    {text}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          messages.map((msg) => {
            const roleClass = msg.role === 'error' ? 'error'
              : msg.role === 'warning' ? 'warning'
              : msg.role;
            const isQna = msg.qnaData && msg.qnaData.task_family === 'qna';
            const isDesignOps = msg.qnaData && (
              msg.qnaData.task_family === 'design_assist' ||
              msg.qnaData.task_family === 'summary' ||
              msg.qnaData.task_family === 'takeoff_estimate'
            );

            return (
              <div key={msg.id} className={`message-wrapper message-wrapper--${roleClass}`}>
                {isDesignOps ? (
                  <>
                    <div className={`message message--${roleClass}`}>{msg.text}</div>
                    <DesignOpsPanel data={msg.qnaData} />
                  </>
                ) : isQna ? (
                  <QnaPanel data={msg.qnaData} />
                ) : (
                  <div className={`message message--${roleClass}`}>
                    {msg.text}
                  </div>
                )}
                {/* Actions row for AI/error messages */}
                {(msg.role === 'ai' || msg.role === 'error') && (
                  <div className="message-actions">
                    <CopyButton text={msg.text} />
                    {msg.role === 'ai' && onRetry && (
                      <button
                        type="button"
                        className="message-actions__btn"
                        onClick={() => onRetry(msg.id)}
                        disabled={loading}
                        aria-label="Retry this message"
                      >
                        Retry
                      </button>
                    )}
                    {msg.elapsed != null && (
                      <span className="message-meta">{msg.elapsed}s</span>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
        {loading && (
          <ProgressIndicator startTime={loadingStartTime || Date.now()} />
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Context-aware follow-up chips (H2) */}
      {followUps.length > 0 && (
        <div className="chat__followups">
          {followUps.map((text) => (
            <button
              key={text}
              type="button"
              className="chat__suggestion"
              onClick={() => setInput(text)}
            >
              {text}
            </button>
          ))}
        </div>
      )}

      {selectedEntities?.length > 0 && (
        <div className="chat-selection-tags" data-testid="chat-selection-tags">
          <span className="entity-tag-count" data-testid="entity-tag-count">{selectedEntities.length} selected</span>
          {selectedEntities.map(ent => (
            <span key={ent.handle} className="entity-tag" data-testid="entity-tag">
              {ent.label}
              <button type="button" data-testid="entity-tag-remove" onClick={() => onRemoveEntity?.(ent.handle)} aria-label={`Remove ${ent.label}`}>&times;</button>
            </span>
          ))}
          <button type="button" className="btn btn--ghost btn--xs" data-testid="clear-selection" onClick={onClearSelection}>Clear</button>
        </div>
      )}

      <form className="chat__input-area" onSubmit={handleSubmit}>
        <div className="chat__input-row">
          <textarea
            ref={textareaRef}
            className="chat__textarea"
            data-testid="chat-textarea"
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? 'Upload a file first...' : 'e.g. Move the north wall 6 inches south'}
            disabled={disabled || loading}
            rows={1}
            aria-label="Edit description"
          />
          <button
            type="submit"
            className="btn btn--primary"
            data-testid="chat-send"
            disabled={!input.trim() || loading || disabled}
            aria-label="Send"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
