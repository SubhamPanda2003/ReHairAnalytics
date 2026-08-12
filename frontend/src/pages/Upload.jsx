import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Loader2, Sparkles } from "lucide-react";
import ViewSlot from "@/components/upload/ViewSlot";
import RegionCaptureOverlay from "@/components/upload/RegionCaptureOverlay";
import { SCAN_REGIONS } from "@/components/upload/constants";

export default function UploadPage() {
  const navigate = useNavigate();
  const [slots, setSlots] = useState({}); // regionKey -> { frames: [{blob, region, sharp}], preview, status, count }
  const [activeRegion, setActiveRegion] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  const storeFrames = (regionKey, frames) => {
    const best = [...frames].sort((a, b) => b.sharp - a.sharp)[0];
    setSlots((s) => ({
      ...s,
      [regionKey]: { frames, preview: URL.createObjectURL(best.blob), status: "done", count: frames.length },
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
    try {
      const res = await api.post("/scan", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Analyzed ${res.data.analysis.frames_used} of ${res.data.analysis.frames_analyzed} photos`);
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
          <p className="text-muted-foreground mt-1">Capture each region one at a time — auto-capture bursts several photos and keeps the sharpest ones for a stable result.</p>
        </div>

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
      </main>

      <RegionCaptureOverlay
        region={activeRegionObj}
        open={!!activeRegion}
        onClose={() => setActiveRegion(null)}
        onCaptured={onCaptured}
      />
    </div>
  );
}
