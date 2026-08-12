import { CircleDot, Scan, Target } from "lucide-react";

export const REGIONS = [
  { key: "full", label: "Full scalp", icon: Scan, tip: "Sweep the phone slowly over your whole head." },
  { key: "crown", label: "Crown", icon: CircleDot, tip: "Tilt your head down and hover over the top-back." },
  { key: "hairline", label: "Hairline", icon: Target, tip: "Hold at forehead height, panning across the front." },
];

export const VIEWS = [
  { key: "front", label: "Front" },
  { key: "top", label: "Top / Crown" },
  { key: "left", label: "Left" },
  { key: "right", label: "Right" },
  { key: "back", label: "Back" },
];

export const REGION_PARAMS = {
  full: {
    duration: 30, interval: 1000, target: 6,
    guides: ["Face the camera straight on", "Slowly turn your head LEFT ⟵", "Now turn your head RIGHT ⟶", "Tilt your head DOWN — show the crown", "Look UP — reveal the hairline", "Turn to show the BACK of your head"],
    regionMap: ["front", "left", "right", "crown", "hairline", "back"],
  },
  crown: { duration: 24, interval: 1800, target: 4, guides: ["Tilt your head down", "Pan slowly over the crown", "Cover the top-back evenly"], regionMap: null },
  hairline: { duration: 24, interval: 1800, target: 4, guides: ["Hold at forehead height", "Pan across your hairline", "Include both temples"], regionMap: null },
};

// Manual mode's per-region burst capture: pick a region, hold steady, the
// camera auto-bursts several shots and keeps the single sharpest one. Region
// tags match the backend's region-aware scoring (ai_service.HAIRLINE_VISIBLE_REGIONS
// etc.), not the VIEWS naming above -- kept separate from auto-scan's REGIONS/
// REGION_PARAMS since it's a distinct, per-region-at-a-time flow.
export const SCAN_REGIONS = [
  { key: "front", label: "Front", guide: "Face the camera straight on" },
  { key: "left", label: "Left", guide: "Turn your head LEFT, showing your left side" },
  { key: "right", label: "Right", guide: "Turn your head RIGHT, showing your right side" },
  { key: "crown", label: "Crown", guide: "Tilt your head down, camera above, showing your crown" },
  { key: "hairline", label: "Hairline", guide: "Hold at forehead height, showing your hairline" },
  { key: "back", label: "Back", guide: "Show the back of your head" },
];

export const BURST_INTERVAL_MS = 800;
export const BURST_TARGET = 10; // frames captured per region
export const BURST_DURATION_S = (BURST_TARGET * BURST_INTERVAL_MS) / 1000;
export const BURST_KEEP = 1; // only the single sharpest frame per region is kept
