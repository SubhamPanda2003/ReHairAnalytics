import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Gauge, Loader2, Scan, Sparkles, UploadCloud } from "lucide-react";
import AutoScan from "@/components/upload/AutoScan";
import ViewSlot from "@/components/upload/ViewSlot";
import RegionCaptureOverlay from "@/components/upload/RegionCaptureOverlay";
import { SCAN_REGIONS } from "@/components/upload/constants";

export default function UploadPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("auto");
  // Re-checks each region's reading a couple extra times and blends them,
  // trading scan time for steadier scores. On by default -- a 42-photo real
  // -Gemini eval found single-read scores only weakly correlated with known
  // severity (r=-0.44); ensembling is the existing, already-shipped fix for
  // that specific noise source. User can still opt out for a faster scan.
  // Sent to /scan as "precision".
  const [precision, setPrecision] = useState(true);

  // Manual mode: per-region burst capture, accumulated client-side until one
  // final /scan submission covering every captured region.
  const [slots, setSlots] = useState({}); // regionKey -> { frames, preview, status }
  const [activeRegion, setActiveRegion] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  // Previous scan's best photo per region, shown as a translucent ghost
  // overlay during capture so the user can line up the same way as last time.
  const { data: lastPhotos } = useQuery({
    queryKey: ["last-photos"],
    queryFn: () => api.get("/sessions/last-photos").then((r) => r.data.photos || {}),
    staleTime: 60_000,
  });

  const storeFrames = (regionKey, frames) => {
    const best = [...frames].sort((a, b) => b.sharp - a.sharp)[0];
    setSlots((s) => ({
      ...s,
      [regionKey]: { frames, preview: URL.createObjectURL(best.blob), status: "done" },
    }));
  };

  const onCaptured = (regionKey, frames) => storeFrames(regionKey, frames);
  const onFile = (regionKey, file) => storeFrames(regionKey, [{ blob: file, region: regionKey, sharp: Infinity }]);

  const doneCount = Object.values(slots).filter((s) => s.status === "done").length;

  const analyze = async () => {
    if (doneCount === 0) { toast.error("Capture at least one region"); return; }
    setAnalyzing(true);
    const fd = new FormData();
    let i = 0;
    for (const slot of Object.values(slots)) {
      for (const f of slot.frames) {
        fd.append("files", f.blob, `frame_${i}.jpg`);
        fd.append("frame_regions", f.region);
        i += 1;
      }
    }
    fd.append("region", "full");
    fd.append("precision", precision ? "true" : "false");
    try {
      // /scan hands the actual analysis off to a background job and returns
      // right away -- Results polls the session until it's done.
      const res = await api.post("/scan", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Photos captured — analyzing now.");
      navigate(`/results/${res.data.session_id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Analysis failed");
      setAnalyzing(false);
    }
  };

  const activeRegionObj = SCAN_REGIONS.find((r) => r.key === activeRegion) || null;

  return (
    <div className="min-h-screen bg-background" data-testid="upload-page">
      <Navbar />
      <main className="max-w-5xl mx-auto px-5 md:px-8 py-8">
        <div className="mb-6">
          <h1 className="font-heading text-3xl font-bold tracking-tight">New scan</h1>
          <p className="text-muted-foreground mt-1">Auto-scan sweeps through every region in one go. Manual lets you capture (or upload) each region yourself.</p>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div className="inline-flex p-1 rounded-full bg-secondary" data-testid="mode-toggle">
            <button onClick={() => setMode("auto")} data-testid="mode-auto"
              className={`flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-colors duration-200 ${mode === "auto" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>
              <Scan className="w-4 h-4" /> Auto-scan
            </button>
            <button onClick={() => setMode("manual")} data-testid="mode-manual"
              className={`flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-colors duration-200 ${mode === "manual" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>
              <UploadCloud className="w-4 h-4" /> Manual views
            </button>
          </div>

          <button
            onClick={() => setPrecision((v) => !v)}
            data-testid="precision-toggle"
            title="Double-checks each area's reading a couple extra times for steadier scores. Turn off for a quicker scan."
            className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium border transition-colors duration-200 ${precision ? "border-primary bg-accent/50 text-foreground" : "border-border text-muted-foreground hover:bg-secondary"}`}
          >
            <Gauge className="w-4 h-4" /> Precision Mode: {precision ? "On" : "Off"}
          </button>
        </div>

        {mode === "auto" ? (
          <AutoScan precision={precision} ghostPhotos={lastPhotos} />
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
            {SCAN_REGIONS.map((region) => (
              <motion.div key={region.key} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
                <ViewSlot region={region} state={slots[region.key]} onCapture={setActiveRegion} onFile={onFile} />
              </motion.div>
            ))}

            <div className="rounded-2xl border border-border bg-secondary/40 p-6 flex flex-col justify-center">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.15em] text-muted-foreground mb-2"><Sparkles className="w-4 h-4" /> Ready?</div>
              <p className="text-sm text-muted-foreground mb-4">{doneCount} of {SCAN_REGIONS.length} regions captured.</p>
              <Button onClick={analyze} disabled={analyzing || doneCount === 0} className="rounded-full h-11" data-testid="analyze-btn">
                {analyzing ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Analyzing…</> : "Analyze scan"}
              </Button>
            </div>
          </div>
        )}
      </main>

      <RegionCaptureOverlay
        region={activeRegionObj}
        open={!!activeRegion}
        onClose={() => setActiveRegion(null)}
        onCaptured={onCaptured}
        ghostPhotos={lastPhotos}
      />
    </div>
  );
}
