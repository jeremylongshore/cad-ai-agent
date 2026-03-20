import { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import { DxfViewer } from 'dxf-viewer';
import { Color, Vector3 } from 'three';

/**
 * Interactive WebGL DXF viewer powered by dxf-viewer + Three.js.
 *
 * Props:
 *   dxfUrl      — blob URL or direct URL to a DXF file (required)
 *   onPointClick — optional callback ({x, y}) for control point picking
 *   className   — optional container class
 *   pickingMode — when true, show crosshair cursor and emit onPointClick
 *
 * Ref API:
 *   focusOnBounds({ minX, minY, maxX, maxY }) — pan/zoom to bounds with highlight ring
 */
const DxfViewerComponent = forwardRef(function DxfViewerComponent(
  { dxfUrl, onPointClick, className, pickingMode },
  ref,
) {
  const containerRef = useRef(null);
  const viewerRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Highlight overlay state
  const [highlightRect, setHighlightRect] = useState(null);
  const highlightTimerRef = useRef(null);

  // Detect dark mode
  const isDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;

  /** Convert model-space bounds to pixel rect relative to the canvas container. */
  const computeScreenRect = useCallback((bounds) => {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    if (!viewer || !container) return null;

    const cam = viewer.GetCamera?.();
    if (!cam) return null;

    const origin = viewer.GetOrigin();
    const canvas = container.querySelector('canvas');
    if (!canvas) return null;
    const cw = canvas.clientWidth;
    const ch = canvas.clientHeight;

    // Project world corner to NDC via Three.js, then to pixels
    const toPixel = (wx, wy) => {
      const point = new Vector3(wx - origin.x, wy - origin.y, 0);
      point.project(cam);
      return {
        px: ((point.x + 1) / 2) * cw,
        py: ((-point.y + 1) / 2) * ch,
      };
    };

    const topLeft = toPixel(bounds.minX, bounds.maxY);
    const bottomRight = toPixel(bounds.maxX, bounds.minY);

    const left = Math.min(topLeft.px, bottomRight.px);
    const top = Math.min(topLeft.py, bottomRight.py);
    const width = Math.abs(bottomRight.px - topLeft.px);
    const height = Math.abs(bottomRight.py - topLeft.py);

    // Enforce minimum visible size (at least 20px)
    const minSize = 20;
    const adjWidth = Math.max(width, minSize);
    const adjHeight = Math.max(height, minSize);
    const adjLeft = left - (adjWidth - width) / 2;
    const adjTop = top - (adjHeight - height) / 2;

    return { left: adjLeft, top: adjTop, width: adjWidth, height: adjHeight };
  }, []);

  /** Clear any active highlight. */
  const clearHighlight = useCallback(() => {
    clearTimeout(highlightTimerRef.current);
    setHighlightRect(null);
  }, []);

  useImperativeHandle(ref, () => ({
    /** Expose the underlying camera for viewport-based calculations. */
    GetCamera() {
      return viewerRef.current?.GetCamera?.() ?? null;
    },
    focusOnBounds({ minX, minY, maxX, maxY }) {
      const viewer = viewerRef.current;
      if (!viewer) return;

      const origin = viewer.GetOrigin();
      const padX = Math.max((maxX - minX) * 0.2, 50);
      const padY = Math.max((maxY - minY) * 0.2, 50);

      viewer.FitView(
        minX - origin.x - padX,
        maxX - origin.x + padX,
        minY - origin.y - padY,
        maxY - origin.y + padY,
        0.05,
      );

      // Compute screen rect for the highlight overlay after FitView settles
      requestAnimationFrame(() => {
        const rect = computeScreenRect({ minX, minY, maxX, maxY });
        if (rect) {
          clearHighlight();
          setHighlightRect(rect);
          highlightTimerRef.current = setTimeout(() => setHighlightRect(null), 3000);
        }
      });
    },
  }), [computeScreenRect, clearHighlight]);

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

  const handleZoomIn = useCallback(() => {
    const cam = viewerRef.current?.GetCamera?.();
    if (cam) {
      cam.zoom *= 1.3;
      cam.updateProjectionMatrix();
      viewerRef.current.Render();
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    const cam = viewerRef.current?.GetCamera?.();
    if (cam) {
      cam.zoom /= 1.3;
      cam.updateProjectionMatrix();
      viewerRef.current.Render();
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

    let viewer;
    try {
      viewer = new DxfViewer(container, {
        autoResize: true,
        clearColor: new Color(isDark ? '#1a1a2e' : '#ffffff'),
        antialias: true,
        colorCorrection: true,
        blackWhiteInversion: true,
      });
    } catch (err) {
      console.error('[DxfViewer] WebGL init failed:', err);
      setError('WebGL unavailable — try a different browser');
      setLoading(false);
      return;
    }

    if (!viewer.HasRenderer()) {
      setError('WebGL unavailable — try a different browser');
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

    // Dismiss highlight on user pan/zoom interaction
    const dismissHighlight = () => clearHighlight();
    viewer.Subscribe('viewChanged', dismissHighlight);

    viewer
      .Load({ url: dxfUrl, fonts: ['/fonts/NotoSans-Regular.ttf'], progressCbk: null })
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
      viewer.Unsubscribe('viewChanged', dismissHighlight);
      viewer.Destroy();
      viewerRef.current = null;
    };
  }, [dxfUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  // Clean up timer on unmount
  useEffect(() => {
    return () => clearTimeout(highlightTimerRef.current);
  }, []);

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

      {highlightRect && (
        <div
          className="viewer-focus-highlight"
          style={{
            left: highlightRect.left,
            top: highlightRect.top,
            width: highlightRect.width,
            height: highlightRect.height,
          }}
        />
      )}

      <div className="viewer-toolbar">
        <button
          className="viewer-toolbar__btn"
          onClick={handleZoomIn}
          title="Zoom in"
          aria-label="Zoom in"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="5" />
            <path d="M8 5.5v5M5.5 8h5" />
          </svg>
        </button>
        <button
          className="viewer-toolbar__btn"
          onClick={handleZoomOut}
          title="Zoom out"
          aria-label="Zoom out"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="5" />
            <path d="M5.5 8h5" />
          </svg>
        </button>
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
      <span className="viewer-toolbar__hint">Scroll to zoom · Drag to pan</span>
    </div>
  );
});

export default DxfViewerComponent;
