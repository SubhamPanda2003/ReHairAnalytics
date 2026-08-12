import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Loader2, Scan, Sparkles, UploadCloud } from "lucide-react";
import AutoScan from "@/components/upload/AutoScan";
import CameraDialog from "@/components/upload/CameraDialog";
import ViewSlot from "@/components/upload/ViewSlot";
import { VIEWS } from "@/components/upload/constants";

export default function UploadPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("auto");
  const [sessionId, setSessionId] = useState(null);
  const [slots, setSlots] = useState({});
  const [camView, setCamView] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const res = await api.post("/sessions", { notes: "" });
    setSessionId(res.data.id);
    return res.data.id;
  };

  const uploadFile = async (view, file) => {
    const preview = URL.createObjectURL(file);
    setSlots((s) => ({ ...s, [view]: { preview, status: "uploading" } }));
    let sid;
    try {
      sid = await ensureSession();
    } catch (e) {
      setSlots((s) => ({ ...s, [view]: { preview, status: "rejected", issues: ["Could not start a session"] } }));
      toast.error("Could not start a session");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("view", view);
    try {
      const res = await api.post(`/sessions/${sid}/upload`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      if (res.data.rejected) {
        setSlots((s) => ({ ...s, [view]: { preview, status: "rejected", issues: res.data.issues, quality: res.data.quality_score } }));
        toast.warning(`${view} rejected — quality ${res.data.quality_score}`);
      } else {
        setSlots((s) => ({ ...s, [view]: { preview, status: "done", quality: res.data.quality_score } }));
        toast.success(`${view} accepted (quality ${res.data.quality_score})`);
      }
    } catch (e) {
      setSlots((s) => ({ ...s, [view]: { preview, status: "rejected", issues: [e.response?.data?.detail || "Upload failed"] } }));
      toast.error(e.response?.data?.detail || "Upload failed");
    }
  };

  const doneCount = Object.values(slots).filter((s) => s.status === "done").length;

  const analyze = async () => {
    if (doneCount === 0) { toast.error("Upload at least one accepted photo"); return; }
    setAnalyzing(true);
    try {
      await api.post(`/sessions/${sessionId}/analyze`);
      toast.success("Analysis complete");
      navigate(`/results/${sessionId}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Analysis failed");
      setAnalyzing(false);
    }
  };

  return (
    <div className="min-h-screen bg-background" data-testid="upload-page">
      <Navbar />
      <main className="max-w-5xl mx-auto px-5 md:px-8 py-8">
        <div className="mb-6">
          <h1 className="font-heading text-3xl font-bold tracking-tight">New scan</h1>
          <p className="text-muted-foreground mt-1">Auto-scan captures many photos as you move, then averages all the sharp ones for a stable result. Prefer control? Switch to manual.</p>
        </div>

        <div className="inline-flex p-1 rounded-full bg-secondary mb-8" data-testid="mode-toggle">
          <button onClick={() => setMode("auto")} data-testid="mode-auto"
            className={`flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-colors duration-200 ${mode === "auto" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>
            <Scan className="w-4 h-4" /> Auto-scan
          </button>
          <button onClick={() => setMode("manual")} data-testid="mode-manual"
            className={`flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-colors duration-200 ${mode === "manual" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>
            <UploadCloud className="w-4 h-4" /> Manual views
          </button>
        </div>

        {mode === "auto" ? (
          <AutoScan />
        ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {VIEWS.map((v) => (
            <motion.div key={v.key} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
              <ViewSlot view={v} state={slots[v.key]} onFile={uploadFile} onCamera={(k) => setCamView(k)} />
            </motion.div>
          ))}

          <div className="rounded-2xl border border-border bg-secondary/40 p-6 flex flex-col justify-center">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.15em] text-muted-foreground mb-2"><Sparkles className="w-4 h-4" /> Ready?</div>
            <p className="text-sm text-muted-foreground mb-4">{doneCount} of 5 views accepted.</p>
            <Button onClick={analyze} disabled={analyzing || doneCount === 0} className="rounded-full h-11" data-testid="analyze-btn">
              {analyzing ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Analyzing…</> : "Analyze scan"}
            </Button>
          </div>
        </div>
        )}
      </main>

      <CameraDialog open={!!camView} onClose={() => setCamView(null)} onCapture={(file) => camView && uploadFile(camView, file)} />
    </div>
  );
}
