import { CheckCircle2, AlertTriangle } from "lucide-react";
import useDeviceTilt from "@/hooks/useDeviceTilt";

// Matches the backend's own finding: a 3-degree rotation alone swung an AI
// score 30->65 (see CAPTURE_NOISE_FLOOR's docstring). A small cushion above
// that avoids a hair-trigger indicator flickering on ordinary sensor jitter.
const LEVEL_THRESHOLD_DEG = 4;

/** Advisory-only "hold phone level" nudge shown during capture, backed by
 * the device's orientation sensor. Purely a visual hint -- never blocks or
 * delays capture, and renders nothing at all when the sensor is unsupported,
 * permission was denied, or no readings ever arrive (see useDeviceTilt). */
export default function TiltIndicator({ active, className = "", light = false }) {
  const { supported, tilt } = useDeviceTilt(active);
  if (!supported) return null;

  const level = tilt < LEVEL_THRESHOLD_DEG;
  const cls = level
    ? "bg-primary/15 text-primary"
    : light
      ? "bg-amber-500/20 text-amber-700"
      : "bg-amber-500/20 text-amber-400";

  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full w-fit ${cls} ${className}`}
      data-testid="tilt-indicator"
      data-level={level ? "true" : "false"}
    >
      {level ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
      {level ? "Phone level" : "Hold phone level"}
    </span>
  );
}
