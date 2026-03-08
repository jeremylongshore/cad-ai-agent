import { useState, useEffect, useCallback } from 'react';
import { fetchProfiles } from '../lib/api';

/**
 * CompareFromLibrary — modal to pick two library documents and kick off a comparison.
 *
 * Usage:
 *   <CompareFromLibrary
 *     documents={documents}
 *     onCompare={compareDocuments}   // (masterDocId, revisionDocId, profile) => Promise
 *     onClose={() => setOpen(false)}
 *   />
 */

function truncateFilename(name, max = 30) {
  if (!name || name.length <= max) return name;
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')) : '';
  return name.slice(0, max - ext.length - 1) + '…' + ext;
}

export default function CompareFromLibrary({ documents, onCompare, onClose }) {
  const [masterDocId, setMasterDocId] = useState(null);
  const [revisionDocId, setRevisionDocId] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState(null);

  // Fetch available comparison profiles
  useEffect(() => {
    fetchProfiles()
      .then((data) => setProfiles(data.profiles || []))
      .catch(() => { /* profiles optional */ });
  }, []);

  // Close on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleCompare = useCallback(async () => {
    if (!masterDocId || !revisionDocId) return;
    if (masterDocId === revisionDocId) {
      setError('Master and Revision must be different documents.');
      return;
    }
    setError(null);
    setComparing(true);
    try {
      await onCompare(masterDocId, revisionDocId, selectedProfile || null);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setComparing(false);
    }
  }, [masterDocId, revisionDocId, selectedProfile, onCompare, onClose]);

  const canCompare = masterDocId && revisionDocId && masterDocId !== revisionDocId;

  return (
    /* Backdrop */
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Compare documents from library"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'var(--surface-overlay)',
        backdropFilter: 'blur(4px)',
        zIndex: 'var(--z-modal)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-4)',
      }}
    >
      {/* Modal panel */}
      <div style={{
        background: 'var(--surface-card)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-5)',
        width: '100%',
        maxWidth: 480,
        boxShadow: 'var(--shadow-xl)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
        maxHeight: '90vh',
        overflow: 'auto',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 style={{
            margin: 0,
            fontSize: 'var(--text-base)',
            fontWeight: 700,
            fontFamily: 'var(--font-display)',
            color: 'var(--text-primary)',
          }}>
            Compare from Library
          </h2>
          <button
            className="btn btn--ghost btn--sm"
            onClick={onClose}
            aria-label="Close compare dialog"
            style={{ cursor: 'pointer' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Instructions */}
        <p style={{ margin: 0, fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
          Select a Master (baseline) and a Revision document to compare side-by-side.
        </p>

        {/* Document selector: Master */}
        <DocumentSelector
          label="Master (baseline)"
          accent="var(--accent-primary)"
          documents={documents}
          selectedId={masterDocId}
          disabledId={revisionDocId}
          onSelect={setMasterDocId}
        />

        {/* Document selector: Revision */}
        <DocumentSelector
          label="Revision"
          accent="var(--accent-success)"
          documents={documents}
          selectedId={revisionDocId}
          disabledId={masterDocId}
          onSelect={setRevisionDocId}
        />

        {/* Profile selector (optional) */}
        {profiles.length > 0 && (
          <div className="input-group">
            <label className="input-group__label" htmlFor="compare-profile">
              Comparison profile (optional)
            </label>
            <select
              id="compare-profile"
              className="input-group__field"
              value={selectedProfile}
              onChange={(e) => setSelectedProfile(e.target.value)}
              style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', cursor: 'pointer' }}
            >
              <option value="">Default</option>
              {profiles.map((p) => (
                <option key={p.id || p.name} value={p.id || p.name}>
                  {p.label || p.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Error */}
        {error && (
          <p style={{
            margin: 0,
            fontSize: 'var(--text-sm)',
            color: 'var(--accent-danger)',
            background: 'var(--accent-danger-light)',
            padding: 'var(--space-2) var(--space-3)',
            borderRadius: 'var(--radius-md)',
            borderLeft: '3px solid var(--accent-danger)',
          }}>
            {error}
          </p>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
          <button
            className="btn btn--ghost btn--sm"
            onClick={onClose}
            disabled={comparing}
            style={{ cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            className="btn btn--primary btn--sm"
            onClick={handleCompare}
            disabled={!canCompare || comparing}
            style={{ cursor: canCompare && !comparing ? 'pointer' : 'not-allowed' }}
          >
            {comparing ? (
              <><span className="spinner" style={{ width: 12, height: 12 }} aria-hidden="true" /> Comparing...</>
            ) : 'Compare'}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Inner sub-component: scrollable list for picking one document */
function DocumentSelector({ label, accent, documents, selectedId, disabledId, onSelect }) {
  return (
    <div>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        marginBottom: 'var(--space-2)',
      }}>
        <span style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: accent,
          flexShrink: 0,
        }} aria-hidden="true" />
        <span style={{
          fontSize: 'var(--text-sm)',
          fontWeight: 600,
          color: 'var(--text-primary)',
        }}>
          {label}
        </span>
        {selectedId && (
          <span style={{
            marginLeft: 'auto',
            fontSize: 'var(--text-xs)',
            color: accent,
          }}>
            selected
          </span>
        )}
      </div>
      <div style={{
        maxHeight: 180,
        overflowY: 'auto',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)',
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        background: 'var(--bg-secondary)',
      }}>
        {documents.map((doc) => {
          const isSelected = selectedId === doc.doc_id;
          const isDisabled = disabledId === doc.doc_id;
          return (
            <button
              key={doc.doc_id}
              onClick={() => !isDisabled && onSelect(isSelected ? null : doc.doc_id)}
              disabled={isDisabled}
              aria-pressed={isSelected}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                padding: 'var(--space-2) var(--space-3)',
                background: isSelected ? 'var(--accent-primary-light)' : 'var(--bg-primary)',
                borderLeft: isSelected ? `3px solid ${accent}` : '3px solid transparent',
                border: 'none',
                borderBottom: '1px solid var(--border-default)',
                cursor: isDisabled ? 'not-allowed' : 'pointer',
                opacity: isDisabled ? 0.45 : 1,
                textAlign: 'left',
                fontFamily: 'var(--font-body)',
                width: '100%',
                transition: 'background var(--transition-fast)',
              }}
              onMouseEnter={(e) => {
                if (!isSelected && !isDisabled) e.currentTarget.style.background = 'var(--bg-tertiary)';
              }}
              onMouseLeave={(e) => {
                if (!isSelected) e.currentTarget.style.background = 'var(--bg-primary)';
              }}
            >
              {/* Checkmark or blank */}
              <span style={{ width: 14, flexShrink: 0, color: accent }}>
                {isSelected && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </span>
              <span style={{
                fontSize: 'var(--text-sm)',
                color: isSelected ? accent : 'var(--text-primary)',
                fontWeight: isSelected ? 500 : 400,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
                title={doc.filename}
              >
                {truncateFilename(doc.filename)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
