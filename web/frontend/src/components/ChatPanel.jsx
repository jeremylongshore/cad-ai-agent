import { useState, useRef, useEffect } from 'react';

const SUGGESTIONS = [
  'Move column A1 24 feet east',
  'Delete the north elevation note',
  'Rename label FOOTING F1 to FOOTING F2',
  'Add a column mark at grid B3',
];

export default function ChatPanel({ messages, onSend, onClear, loading, disabled }) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading || disabled) return;
    onSend(trimmed);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInput = (e) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  return (
    <div className="chat">
      {messages.length > 0 && onClear && (
        <div className="chat__toolbar">
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
      <div className="chat__messages" role="log" aria-label="Chat messages">
        {messages.length === 0 ? (
          <div className="chat__empty">
            <p className="chat__empty-title">Describe your edit</p>
            <p className="chat__empty-text">
              I can move entities, edit text, delete elements, and add blocks.
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
          messages.map((msg, i) => (
            <div key={i} className={`message message--${msg.role}`}>
              {msg.text}
            </div>
          ))
        )}
        {loading && (
          <div className="message message--ai">
            <span className="spinner" aria-label="Thinking..." />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat__input-area" onSubmit={handleSubmit}>
        <div className="chat__input-row">
          <textarea
            ref={textareaRef}
            className="chat__textarea"
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
            disabled={!input.trim() || loading || disabled}
            aria-label="Send"
          >
            {loading ? <span className="spinner" aria-hidden="true" /> : 'Send'}
          </button>
        </div>
      </form>
    </div>
  );
}
