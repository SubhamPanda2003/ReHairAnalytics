import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { UploadCloud, Camera, Check, AlertTriangle, X, Loader2, Sparkles, RotateCcw } from "lucide-react";

const VIEWS = [
  { key: "front", label: "Front" },
  { key: "top", label: "Top / Crown" },
  { key: "left", label: "Left" },
  { key: "right", label: "Right" },
  { key: "back", label: "Back" },
];

const Silhouette = () => (
  <svg viewBox="0 0 200 200" className="absolute inset-0 w-full h-full opacity-50 pointer-events-none" aria-hidden="true">
    <ellipse cx="100" cy="95" rx="55" ry="70" fill="none" stroke="white" strokeWidth="2" strokeDasharray="6 6" />
    <line x1="45" y1="85" x2="155" y2="85" stroke="white" strokeWidth="1.5" strokeDasharray="4 4" />
    <circle cx="80" cy="85" r="4" fill="none" stroke="white" strokeWidth="1.5" />
    <circle cx="120" cy="85" r="4" fill="none" stroke="white" strokeWidth="1.5" />
  </svg>
);

function CameraDialog({ open, onClose, onCapture }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!open) return;
    let active = true;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
        if (!active) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; setReady(true); }
      } catch (e) {
        toast.error("Camera unavailable. Use drag & drop instead.");
        onClose();
      }
    })();
    return () => { active = false; streamRef.current?.getTracks().forEach((t) => t.stop()); setReady(false); };
  }, [open, onClose]);

  const snap = () => {
    const v = videoRef.current;
    if (!v) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    canvas.getContext("2d").drawImage(v, 0, 0);
    canvas.toBlob((blob) => {
      const file = new File([blob], `capture_${Date.now()}.jpg`, { type: "image/jpeg" });
      onCapture(file);
      onClose();
    }, "image/jpeg", 0.92);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md rounded-3xl" data-testid="camera-dialog">
        <DialogHeader><DialogTitle className="font-heading">Align & capture</DialogTitle></DialogHeader>
        <div className="relative rounded-2xl overflow-hidden bg-black aspect-square">
          <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
          <Silhouette />
          <div className="absolute top-3 left-0 right-0 flex justify-center">
            <span className="glass text-xs px-3 py-1.5 rounded-full">Line up eyes & ears · hold steady</span>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-[11px] text-muted-foreground mt-1">
          <span className="text-center">↑ Raise phone</span><span className="text-center">↔ Center head</span><span className="text-center">◎ Fill the outline</span>
        </div>
        <Button onClick={snap} disabled={!ready} className="rounded-full h-11 mt-2" data-testid="camera-capture-btn">
          <Camera className="w-4 h-4 mr-1.5" /> Capture
        </Button>
      </DialogContent>
    </Dialog>
  );
}

function ViewSlot({ view, state, onFile, onCamera }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(view.key, f);
  };

  return (
    <div className="rounded-2xl border border-border bg-card p-4" data-testid={`slot-${view.key}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="font-heading font-semibold">{view.label}</span>
        {state?.status === "done" && <span className="text-xs text-primary flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Q{state.quality}</span>}
        {state?.status === "rejected" && <span className="text-xs text-destructive flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Retry</span>}
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={handleDrop}
        className={`relative rounded-2xl overflow-hidden aspect-square flex items-center justify-center border-2 border-dashed transition-colors duration-200 ${drag ? "border-primary bg-accent/40" : "border-border bg-secondary/40"}`}
      >
        {state?.preview ? (
          <>
            <img src={state.preview} alt={view.key} className="absolute inset-0 w-full h-full object-cover" />
            {state.status === "uploading" && <div className="absolute inset-0 bg-black/50 flex items-center justify-center"><Loader2 className="w-6 h-6 text-white animate-spin" /></div>}
          </>
        ) : (
          <div className="text-center px-4">
            <Silhouette />
            <UploadCloud className="w-7 h-7 text-muted-foreground mx-auto mb-2 relative" />
            <p className="text-xs text-muted-foreground relative">Drag & drop or choose</p>
          </div>
        )}
      </div>

      {state?.status === "rejected" && (
        <p className="text-[11px] text-destructive mt-2">{(state.issues || []).join(", ") || "Quality too low"}</p>
      )}

      <div className="flex gap-2 mt-3">
        <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/jpg" className="hidden"
          onChange={(e) => e.target.files?.[0] && onFile(view.key, e.target.files[0])} data-testid={`file-input-${view.key}`} />
        <Button variant="outline" size="sm" className="flex-1 rounded-full" onClick={() => inputRef.current?.click()} data-testid={`choose-${view.key}`}>
          {state?.status === "rejected" ? <RotateCcw className="w-3.5 h-3.5 mr-1" /> : <UploadCloud className="w-3.5 h-3.5 mr-1" />} File
        </Button>
        <Button variant="outline" size="sm" className="flex-1 rounded-full" onClick={() => onCamera(view.key)} data-testid={`camera-${view.key}`}>
          <Camera className="w-3.5 h-3.5 mr-1" /> Camera
        </Button>
      </div>
    </div>
  );
}

export default function UploadPage() {
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState(null);
  const [slots, setSlots] = useState({});
  const [camView, setCamView] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.post("/sessions", { notes: "" });
        setSessionId(res.data.id);
      } catch (e) { toast.error("Could not start a session"); }
    })();
  }, []);

  const uploadFile = async (view, file) => {
    if (!sessionId) return;
    const preview = URL.createObjectURL(file);
    setSlots((s) => ({ ...s, [view]: { preview, status: "uploading" } }));
    const fd = new FormData();
    fd.append("file", file);
    fd.append("view", view);
    try {
      const res = await api.post(`/sessions/${sessionId}/upload`, fd, { headers: { "Content-Type": "multipart/form-data" } });
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
        <div className="mb-8">
          <h1 className="font-heading text-3xl font-bold tracking-tight">New scan</h1>
          <p className="text-muted-foreground mt-1">Capture standardized views. The Top / Crown view drives your primary density estimate.</p>
        </div>

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
      </main>

      <CameraDialog open={!!camView} onClose={() => setCamView(null)} onCapture={(file) => camView && uploadFile(camView, file)} />
    </div>
  );
}
