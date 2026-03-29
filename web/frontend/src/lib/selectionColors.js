/**
 * Shared 6-color palette for entity selection highlights.
 * Used by DxfViewerComponent (overlay boxes) and ChatPanel (entity tags)
 * so the colors match across both views.
 */
export const SELECTION_COLORS = [
  { border: 'rgba(59,130,246,0.8)',  bg: 'rgba(59,130,246,0.10)',  shadow: 'rgba(59,130,246,0.3)' },   // blue
  { border: 'rgba(16,185,129,0.8)',  bg: 'rgba(16,185,129,0.10)',  shadow: 'rgba(16,185,129,0.3)' },   // emerald
  { border: 'rgba(245,158,11,0.8)',  bg: 'rgba(245,158,11,0.10)',  shadow: 'rgba(245,158,11,0.3)' },   // amber
  { border: 'rgba(168,85,247,0.8)',  bg: 'rgba(168,85,247,0.10)',  shadow: 'rgba(168,85,247,0.3)' },   // purple
  { border: 'rgba(236,72,153,0.8)',  bg: 'rgba(236,72,153,0.10)',  shadow: 'rgba(236,72,153,0.3)' },   // pink
  { border: 'rgba(6,182,212,0.8)',   bg: 'rgba(6,182,212,0.10)',   shadow: 'rgba(6,182,212,0.3)' },    // cyan
];
