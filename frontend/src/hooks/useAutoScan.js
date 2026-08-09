import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { REGION_PARAMS } from "@/components/upload/constants";

/** Drives the guided selfie-camera capture loop: timed frame grabs, a live
 * sharpness score per frame, and uploading the sharpest ones to /scan. */
export default function useAutoScan() {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const framesRef = useRef([]);
  const timersRef = useRef({ cap: null, prog: null, final: null });

  const [region, setRegion] = useState("full");
  const [phase, setPhase] = useState("idle"); // idle | scanning | uploading
  const [progress, setProgress] = useState(0);
  const [count, setCount] = useState(0);
  const [guide, setGuide] = useState("");
  const [screenLight, setScreenLight] = useState(true);

  const params = REGION_PARAMS[region];

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const clearTimers = () => {
    const t = timersRef.current;
    clearInterval(t.cap); clearInterval(t.prog); clearTimeout(t.final);
    t.cap = t.prog = t.final = null;
  };

  const uploadFrames = async () => {
    setPhase("uploading");
    // Pick the best (sharpest) frame per region for a full scan; else the sharpest few.
    let selected;
    if (region === "full") {
      const byRegion = {};
      framesRef.current.forEach((f) => { if (!byRegion[f.region] || f.sharp > byRegion[f.region].sharp) byRegion[f.region] = f; });
      selected = Object.values(byRegion);
    } else {
      selected = [...framesRef.current].sort((a, b) => b.sharp - a.sharp).slice(0, 4);
    }
    if (selected.length === 0) selected = framesRef.current.slice(0, 1);

    const fd = new FormData();
    selected.forEach((f, i) => { fd.append("files", f.blob, `frame_${i}.jpg`); fd.append("frame_regions", f.region); });
    fd.append("region", region);
    try {
      const res = await api.post("/scan", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const a = res.data.analysis;
      toast.success(region === "full" ? `Analyzed best photo from ${a.frames_used} regions` : `Analyzed ${a.frames_used} of ${a.frames_analyzed} photos`);
      navigate(`/results/${res.data.session_id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Scan analysis failed");
      setPhase("idle");
    }
  };

  const start = async () => {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 1280, height: 1280 } });
    } catch (e) {
      toast.error(e?.name === "NotAllowedError" ? "Camera permission denied. Allow access or use manual upload." : "Camera unavailable. Use manual upload instead.");
      return;
    }
    streamRef.current = stream;
    framesRef.current = [];
    setCount(0); setProgress(0); setGuide(params.guides[0]); setPhase("scanning");

    const canvas = document.createElement("canvas");
    const sharpCanvas = document.createElement("canvas");
    sharpCanvas.width = 96; sharpCanvas.height = 96;
    const started = Date.now();

    const sharpness = () => {
      const v = videoRef.current;
      if (!v || !v.videoWidth) return 0;
      const ctx = sharpCanvas.getContext("2d");
      ctx.drawImage(v, 0, 0, 96, 96);
      const d = ctx.getImageData(0, 0, 96, 96).data;
      let sum = 0, prev = 0;
      for (let i = 0; i < d.length; i += 4) {
        const g = d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114;
        if (i > 0) { const df = g - prev; sum += df * df; }
        prev = g;
      }
      return sum;
    };

    const capture = () => {
      const v = videoRef.current;
      if (!v || !v.videoWidth) return;
      const el = (Date.now() - started) / 1000;
      const seg = Math.min(params.guides.length - 1, Math.floor(el / (params.duration / params.guides.length)));
      const fr = params.regionMap ? params.regionMap[seg] : region;
      const sharp = sharpness();
      canvas.width = v.videoWidth; canvas.height = v.videoHeight;
      canvas.getContext("2d").drawImage(v, 0, 0);
      canvas.toBlob((b) => { if (b) { framesRef.current.push({ blob: b, region: fr, sharp }); setCount(framesRef.current.length); } }, "image/jpeg", 0.9);
    };

    timersRef.current.cap = setInterval(capture, params.interval);
    setTimeout(capture, 600);
    timersRef.current.prog = setInterval(() => {
      const el = (Date.now() - started) / 1000;
      setProgress(Math.min(100, (el / params.duration) * 100));
      setGuide(params.guides[Math.min(params.guides.length - 1, Math.floor(el / (params.duration / params.guides.length)))]);
    }, 200);
    timersRef.current.final = setTimeout(() => {
      clearTimers(); setProgress(100); stopStream();
      if (framesRef.current.length === 0) { toast.error("No frames captured"); setPhase("idle"); return; }
      uploadFrames();
    }, params.duration * 1000);
  };

  const cancel = () => {
    clearTimers(); stopStream();
    framesRef.current = []; setCount(0); setProgress(0); setPhase("idle");
  };

  // Attach the live stream once the scanning overlay (and its <video>) is mounted.
  useEffect(() => {
    if (phase === "scanning" && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [phase]);

  // Escape cancels an in-progress scan. `cancel` only touches refs and stable
  // setState setters, so it never goes stale and doesn't need to be a dep.
  useEffect(() => {
    if (phase !== "scanning") return;
    const onKey = (e) => { if (e.key === "Escape") cancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  useEffect(() => () => { clearTimers(); stopStream(); }, []);

  return { videoRef, region, setRegion, phase, progress, count, guide, screenLight, setScreenLight, params, start, cancel };
}
