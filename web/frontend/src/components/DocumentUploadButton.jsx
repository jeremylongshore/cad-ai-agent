import { useRef } from 'react';

/**
 * DocumentUploadButton — compact hidden-input upload trigger for .dxf files.
 *
 * Usage:
 *   <DocumentUploadButton onUpload={uploadToLibrary} loading={libraryLoading} atQuota={atQuota} />
 */

const MAX_SIZE_MB = 50;

export default function DocumentUploadButton({ onUpload, loading = false, atQuota = false }) {
  const inputRef = useRef(null);

  const handleChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (ext !== '.dxf') {
      // Library only accepts DXF (not PDF/DWG — those go via the main upload)
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) return;

    onUpload(file);
  };

  const disabled = loading || atQuota;

  return (
    <>
      <button
        className="btn btn--ghost btn--sm"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        title={atQuota ? 'Document quota reached' : 'Upload DXF to library'}
        aria-label="Upload DXF to library"
        style={{ cursor: disabled ? 'not-allowed' : 'pointer' }}
      >
        {loading ? (
          <span className="spinner" aria-hidden="true" style={{ width: 12, height: 12 }} />
        ) : (
          /* Upload icon (Lucide-style SVG) */
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        )}
        Upload
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".dxf"
        onChange={handleChange}
        style={{ display: 'none' }}
        aria-hidden="true"
      />
    </>
  );
}
