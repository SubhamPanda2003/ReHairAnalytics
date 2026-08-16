import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Sun, SunDim, Volume2, VolumeX, X } from "lucide-react";
import { fileUrl } from "@/lib/api";
import useRegionCapture from "@/hooks/useRegionCapture";
import { BURST_DURATION_S, BURST_KEEP } from "./constants";
import Silhouette from "./Silhouette";

/** Full-screen burst-capture for a single region: auto-fires shots for
 * BURST_DURATION_S seconds and hands the sharpest BURST_KEEP back via
 * onCaptured. Closes itself once capture finishes. */
export default function RegionCaptureOverlay({ region, open, onClose, onCaptured, ghostPhotos }) {
  const {
    videoRef, phase, progress, count, start, cancel, reset,
    screenLight, setScreenLight, voiceOn, setVoiceOn,
  } = useRegionCapture((frames) => {
    onCaptured(region.key, frames);
    onClose();
  });

  useEffect(() => {
    if (open && region) start(region.key, region.guide);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, region?.key]);

  const handleClose = () => { cancel(); reset(); onClose(); };

  if (!open || !region) return null;

  // Last scan's photo of this region, shown very faintly over the live feed
  // so the user can line up the same way as last time.
  const ghostPath = ghostPhotos?.[region.key];

  const size = 300, stroke = 9, r = (size - stroke) / 2, circ = 2 * Math.PI * r;

  return (
    <div
      className={`fixed inset-0 z-[60] flex flex-col items-center justify-center gap-4 sm:gap-6 px-6 py-6 overflow-y-auto transition-colors duration-300 ${screenLight ? "bg-white text-stone-700" : "bg-neutral-900 text-white"}`}
      data-testid="region-capture-overlay"
    >
      <div className="relative rounded-full overflow-hidden shadow-2xl w-[min(70vw,300px)] aspect-square shrink-0" style={{ background: "#000" }}>
        <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover -scale-x-100" />
        {ghostPath && (
          <img
            src={fileUrl(ghostPath)}
            alt=""
            aria-hidden="true"
            data-testid="ghost-overlay"
            className="absolute inset-0 w-full h-full object-cover -scale-x-100 opacity-25 pointer-events-none"
          />
        )}
        <Silhouette pose={region.key} />
        <svg viewBox={`0 0 ${size} ${size}`} className="absolute inset-0 w-full h-full -rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth={stroke} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--primary))" strokeWidth={stroke}
            strokeDasharray={circ} strokeDashoffset={circ - (progress / 100) * circ} strokeLinecap="round" style={{ transition: "stroke-dashoffset 0.2s linear" }} />
        </svg>
      </div>

      <p className="text-xl sm:text-2xl font-heading font-bold text-center max-w-md" data-testid="capture-guide">{region.label}</p>
      <p className="text-sm text-muted-foreground text-center max-w-sm">{region.guide}</p>
      <p className="text-sm font-medium">{count} of ~{Math.round(BURST_DURATION_S * 1000 / 800)} photos · keeping the sharpest {BURST_KEEP}</p>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button variant="outline" onClick={() => setScreenLight((v) => !v)} className={`rounded-full h-11 ${screenLight ? "" : "bg-white/10 border-white/30 text-white hover:bg-white/20"}`} data-testid="light-toggle">
          {screenLight ? <Sun className="w-4 h-4 mr-1.5" /> : <SunDim className="w-4 h-4 mr-1.5" />} Light {screenLight ? "on" : "off"}
        </Button>
        <Button variant="outline" onClick={() => setVoiceOn((v) => !v)} className={`rounded-full h-11 ${screenLight ? "" : "bg-white/10 border-white/30 text-white hover:bg-white/20"}`} data-testid="voice-toggle">
          {voiceOn ? <Volume2 className="w-4 h-4 mr-1.5" /> : <VolumeX className="w-4 h-4 mr-1.5" />} Voice {voiceOn ? "on" : "off"}
        </Button>
        <Button variant="ghost" onClick={handleClose} className={`rounded-full h-11 ${screenLight ? "" : "text-white hover:bg-white/10"}`} data-testid="cancel-capture-btn">
          <X className="w-4 h-4 mr-1.5" /> Cancel
        </Button>
      </div>
      {phase === "idle" && <p className="text-xs text-muted-foreground">Starting camera…</p>}
    </div>
  );
}
