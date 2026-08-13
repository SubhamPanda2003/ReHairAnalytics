import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Camera, Check, RotateCcw, UploadCloud } from "lucide-react";
import Silhouette from "./Silhouette";

/** One region's capture slot: shows a thumbnail of its best captured frame
 * once done, with buttons to (re)run the auto-burst capture or fall back to
 * picking a single file (for when the camera isn't available). Nothing here
 * uploads to the server -- captured/chosen frames are held by the parent and
 * only sent once, when the whole scan is submitted. */
export default function ViewSlot({ region, state, onCapture, onFile }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(region.key, f);
  };

  return (
    <div className="rounded-2xl border border-border bg-card p-4" data-testid={`slot-${region.key}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="font-heading font-semibold">{region.label}</span>
        {state?.status === "done" && (
          <span className="text-xs text-primary flex items-center gap-1" data-testid={`slot-done-${region.key}`}>
            <Check className="w-3.5 h-3.5" /> captured
          </span>
        )}
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={handleDrop}
        className={`relative rounded-2xl overflow-hidden aspect-square flex items-center justify-center border-2 border-dashed transition-colors duration-200 ${drag ? "border-primary bg-accent/40" : "border-border bg-secondary/40"}`}
      >
        {state?.preview ? (
          <img src={state.preview} alt={region.key} className="absolute inset-0 w-full h-full object-cover" />
        ) : (
          <div className="text-center px-4">
            <Silhouette pose={region.key} />
            <UploadCloud className="w-7 h-7 text-muted-foreground mx-auto mb-2 relative" />
            <p className="text-xs text-muted-foreground relative">{region.guide}</p>
          </div>
        )}
      </div>

      <div className="flex gap-2 mt-3">
        <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/jpg" className="hidden"
          onChange={(e) => e.target.files?.[0] && onFile(region.key, e.target.files[0])} data-testid={`file-input-${region.key}`} />
        <Button variant="outline" size="sm" className="flex-1 rounded-full" onClick={() => inputRef.current?.click()} data-testid={`choose-${region.key}`}>
          {state?.status === "done" ? <RotateCcw className="w-3.5 h-3.5 mr-1" /> : <UploadCloud className="w-3.5 h-3.5 mr-1" />} File
        </Button>
        <Button size="sm" className="flex-1 rounded-full" onClick={() => onCapture(region.key)} data-testid={`capture-${region.key}`}>
          <Camera className="w-3.5 h-3.5 mr-1" /> {state?.status === "done" ? "Retake" : "Auto-capture"}
        </Button>
      </div>
    </div>
  );
}
