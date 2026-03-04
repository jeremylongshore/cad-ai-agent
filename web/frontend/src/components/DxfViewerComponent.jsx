import { useEffect, useRef, useState, useCallback } from 'react';
import { DxfViewer } from 'dxf-viewer';
import { Color } from 'three';

/**
 * Interactive WebGL DXF viewer powered by dxf-viewer + Three.js.
 *
 * Props:
 *   dxfUrl      — blob URL or direct URL to a DXF file (required)
 *   onPointClick — optional callback ({x, y}) for control point picking
 *   className   — optional container class
 *   pickingMode — when true, show crosshair cursor and emit onPointClick
 */
export default function DxfViewerComponent({ dxfUrl, onPointClick, className, pickingMode }) {
  const containerRef = useRef(null);
  const viewerRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Detect dark mode
  const isDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;

  const handleFitView = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const bounds = viewer.GetBounds();
    if (bounds) {
      const origin = viewer.GetOrigin();
      viewer.FitView(
        bounds.minX - origin.x,
        bounds.maxX - origin.x,
        bounds.minY - origin.y,
        bounds.maxY - origin.y,
        0.1,
      );
    }
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !dxfUrl) return;

    // Clean up previous viewer
    if (viewerRef.current) {
      viewerRef.current.Destroy();
      viewerRef.current = null;
    }

    setLoading(true);
    setError(null);

    const viewer = new DxfViewer(container, {
      autoResize: true,
      clearColor: new Color(isDark ? '#1a1a2e' : '#ffffff'),
      antialias: true,
      colorCorrection: true,
      blackWhiteInversion: true,
    });

    if (!viewer.HasRenderer()) {
      setError('WebGL not available');
      setLoading(false);
      return;
    }

    viewerRef.current = viewer;

    // Pointer down for control point picking
    const handlePointerDown = (e) => {
      if (onPointClick && e.detail?.position) {
        onPointClick({ x: e.detail.position.x, y: e.detail.position.y });
      }
    };
    viewer.Subscribe('pointerdown', handlePointerDown);

    viewer
      .Load({ url: dxfUrl, fonts: null, progressCbk: null })
      .then(() => {
        setLoading(false);
        // Auto fit after load
        const bounds = viewer.GetBounds();
        if (bounds) {
          const origin = viewer.GetOrigin();
          viewer.FitView(
            bounds.minX - origin.x,
            bounds.maxX - origin.x,
            bounds.minY - origin.y,
            bounds.maxY - origin.y,
            0.1,
          );
        }
      })
      .catch((err) => {
        console.error('[DxfViewer] Load failed:', err);
        setError('Failed to load DXF');
        setLoading(false);
      });

    return () => {
      viewer.Unsubscribe('pointerdown', handlePointerDown);
      viewer.Destroy();
      viewerRef.current = null;
    };
  }, [dxfUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={`dxf-viewer ${className || ''} ${pickingMode ? 'dxf-viewer--picking' : ''}`}>
      <div className="dxf-viewer__canvas" ref={containerRef} />

      {loading && (
        <div className="dxf-viewer__overlay">
          <div className="spinner" aria-hidden="true" />
          <span className="dxf-viewer__overlay-text">Loading drawing...</span>
        </div>
      )}

      {error && (
        <div className="dxf-viewer__overlay dxf-viewer__overlay--error">
          <span className="dxf-viewer__overlay-text">{error}</span>
        </div>
      )}

      <div className="viewer-toolbar">
        <button
          className="viewer-toolbar__btn"
          onClick={handleFitView}
          title="Fit to view"
          aria-label="Fit drawing to view"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="12" height="12" rx="1" />
            <path d="M2 6h4V2M14 6h-4V2M2 10h4v4M14 10h-4v4" />
          </svg>
        </button>
      </div>
    </div>
  );
}
