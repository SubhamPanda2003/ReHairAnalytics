// One unified capture flow: pick a region, hold steady, the camera auto-bursts
// several shots and keeps the sharpest ones -- no separate "auto-scan" vs
// "manual" mode, and no continuous multi-region sweep. Region tags match the
// backend's region-aware scoring (ai_service.HAIRLINE_VISIBLE_REGIONS etc.),
// not the older per-view manual-upload naming.
export const SCAN_REGIONS = [
  { key: "front", label: "Front", guide: "Face the camera straight on" },
  { key: "left", label: "Left", guide: "Turn your head LEFT, showing your left side" },
  { key: "right", label: "Right", guide: "Turn your head RIGHT, showing your right side" },
  { key: "crown", label: "Crown", guide: "Tilt your head down, camera above, showing your crown" },
  { key: "hairline", label: "Hairline", guide: "Hold at forehead height, showing your hairline" },
  { key: "back", label: "Back", guide: "Show the back of your head" },
];

// Burst-capture params, applied per region (not a continuous multi-region sweep).
export const BURST_INTERVAL_MS = 800;
export const BURST_TARGET = 10; // frames captured per region
export const BURST_DURATION_S = (BURST_TARGET * BURST_INTERVAL_MS) / 1000;
export const BURST_KEEP = 4; // sharpest N of the ~10 kept for upload/analysis
