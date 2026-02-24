import { useState, useRef, useCallback } from 'react';

const ACCEPTED_TYPES = ['.dxf', '.pdf'];
const MAX_SIZE_MB = 50;

export default function FileUpload({ onUpload, loading }) {
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const validate = useCallback((file) => {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ACCEPTED_TYPES.includes(ext)) {
      return `Unsupported file type: ${ext}. Use .dxf or .pdf`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large (max ${MAX_SIZE_MB}MB)`;
    }
    return null;
  }, []);

  const handleFile = useCallback((file) => {
    const err = validate(file);
    if (err) {
      setError(err);
      return;
    }
    setError(null);
    onUpload(file);
  }, [validate, onUpload]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragActive(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragActive(false);
  }, []);

  const handleInputChange = useCallback((e) => {
    const file = e.target.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  return (
    <div>
      <div
        className={`upload-zone${dragActive ? ' upload-zone--active' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload a DXF or PDF file"
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
      >
        {loading ? (
          <div className="flex flex-col items-center gap-2">
            <div className="spinner spinner--lg" aria-hidden="true" />
            <p className="upload-zone__text">Uploading and analyzing...</p>
          </div>
        ) : (
          <>
            <div className="upload-zone__icon" aria-hidden="true">&#8679;</div>
            <p className="upload-zone__text">
              Drag and drop your file here, or click to browse
            </p>
            <p className="upload-zone__formats">.dxf, .pdf &mdash; up to {MAX_SIZE_MB}MB</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".dxf,.pdf"
          onChange={handleInputChange}
          style={{ display: 'none' }}
          aria-hidden="true"
        />
      </div>
      {error && <p className="input-group__error mt-2" role="alert">{error}</p>}
    </div>
  );
}
