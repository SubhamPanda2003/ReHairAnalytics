import { Button } from "@/components/ui/button";
import { Camera, Loader2, Play, Sun, SunDim, X } from "lucide-react";
import useAutoScan from "@/hooks/useAutoScan";
import { REGIONS } from "./constants";
import Silhouette from "./Silhouette";

export default function AutoScan() {
  const {
    videoRef, region, setRegion, phase, progress, count, guide,
    screenLight, setScreenLight, params, start, cancel,
  } = useAutoScan();

  const size = 300, stroke = 9, r = (size - stroke) / 2, circ = 2 * Math.PI * r;

  return (
    <>
      <div className="grid lg:grid-cols-5 gap-6" data-testid="autoscan-panel">
        <div className="lg:col-span-2 min-w-0 rounded-3xl border border-border bg-card p-6">
          <h3 className="font-heading font-semibold text-lg mb-1">Choose a focus zone</h3>
          <p className="text-sm text-muted-foreground mb-4">Full scalp keeps the sharpest photo of every angle. Crown & hairline zoom in on one area.</p>
          <div className="space-y-2.5">
            {REGIONS.map((rg) => (
              <button key={rg.key} onClick={() => setRegion(rg.key)} data-testid={`region-${rg.key}`}
                className={`w-full flex items-start gap-3 p-4 rounded-2xl border text-left transition-colors duration-200 ${region === rg.key ? "border-primary bg-accent/50" : "border-border hover:bg-secondary"}`}>
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${region === rg.key ? "bg-primary text-primary-foreground" : "bg-secondary"}`}><rg.icon className="w-4 h-4" /></div>
                <div><p className="font-medium">{rg.label}</p><p className="text-xs text-muted-foreground">{rg.tip}</p></div>
              </button>
            ))}
          </div>
          <div className="mt-4 rounded-2xl bg-secondary/50 p-3 text-xs text-muted-foreground">
            Tip: uses your selfie camera. In a dim room keep Screen light on — the screen turns bright white to light up your face during the scan.
          </div>
        </div>

        <div className="lg:col-span-3 rounded-3xl border border-border bg-card p-6 flex flex-col items-center justify-center">
          <div className="relative rounded-3xl overflow-hidden bg-secondary flex items-center justify-center" style={{ width: 260, height: 260 }}>
            <Silhouette />
            <div className="text-center relative">
              <Camera className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">Selfie camera preview<br />appears full-screen on start</p>
            </div>
          </div>
          <p className="text-sm text-muted-foreground mt-4 text-center">Move for {params.duration}s while it captures — we keep the sharpest photo of each area.</p>
          <div className="flex items-center gap-3 mt-4">
            <Button onClick={start} className="rounded-full h-12 px-8 text-base" data-testid="start-scan-btn">
              <Play className="w-5 h-5 mr-1.5" /> Start {params.duration}s scan
            </Button>
            <Button variant="outline" onClick={() => setScreenLight((v) => !v)} className="rounded-full h-12" data-testid="light-btn">
              {screenLight ? <Sun className="w-4 h-4 mr-1.5" /> : <SunDim className="w-4 h-4 mr-1.5" />} Screen light {screenLight ? "on" : "off"}
            </Button>
          </div>
        </div>
      </div>

      {phase !== "idle" && (
        <div className={`fixed inset-0 z-[60] flex flex-col items-center justify-center gap-6 px-6 transition-colors duration-300 ${screenLight ? "bg-white text-stone-700" : "bg-neutral-900 text-white"}`} data-testid="scan-overlay">
          <div className="relative rounded-full overflow-hidden shadow-2xl" style={{ width: size, height: size, background: "#000" }}>
            <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover -scale-x-100" />
            <svg className="absolute inset-0 -rotate-90" width={size} height={size}>
              <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth={stroke} />
              <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--primary))" strokeWidth={stroke}
                strokeDasharray={circ} strokeDashoffset={circ - (progress / 100) * circ} strokeLinecap="round" style={{ transition: "stroke-dashoffset 0.2s linear" }} />
            </svg>
            {phase === "uploading" && <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-2 text-white"><Loader2 className="w-7 h-7 animate-spin" /><span className="text-sm">Averaging photos…</span></div>}
          </div>

          {phase === "scanning" ? (
            <>
              <p className="text-2xl font-heading font-bold text-center max-w-md" data-testid="scan-guide">{guide}</p>
              <p className="text-sm font-medium">{count} photos · {Math.round(progress)}%</p>
              <div className="flex items-center gap-3">
                <Button variant="outline" onClick={() => setScreenLight((v) => !v)} className={`rounded-full h-11 ${screenLight ? "" : "bg-white/10 border-white/30 text-white hover:bg-white/20"}`} data-testid="light-toggle">
                  {screenLight ? <Sun className="w-4 h-4 mr-1.5" /> : <SunDim className="w-4 h-4 mr-1.5" />} Light {screenLight ? "on" : "off"}
                </Button>
                <Button variant="ghost" onClick={cancel} className={`rounded-full h-11 ${screenLight ? "" : "text-white hover:bg-white/10"}`} data-testid="cancel-scan-btn">
                  <X className="w-4 h-4 mr-1.5" /> Cancel
                </Button>
              </div>
            </>
          ) : (
            <p className="text-lg font-medium">Analyzing your photos…</p>
          )}
        </div>
      )}
    </>
  );
}
