import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Camera } from "lucide-react";
import Silhouette from "./Silhouette";

export default function CameraDialog({ open, onClose, onCapture }) {
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
