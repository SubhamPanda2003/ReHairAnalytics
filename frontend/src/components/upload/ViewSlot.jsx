import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Camera, Check, Loader2, RotateCcw, UploadCloud } from "lucide-react";
import Silhouette from "./Silhouette";

export default function ViewSlot({ view, state, onFile, onCamera }) {
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
