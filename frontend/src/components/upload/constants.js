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
