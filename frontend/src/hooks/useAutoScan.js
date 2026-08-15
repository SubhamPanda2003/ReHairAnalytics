import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { REGION_PARAMS, POSE_COUNTDOWN_S } from "@/components/upload/constants";

/** Drives the guided selfie-camera capture loop: for each pose in sequence,
 * announce it, give the user a POSE_COUNTDOWN_S countdown to get into
 * position (no frames captured during that window), then fire timed frame
 * grabs with a live sharpness score until it's time for the next pose.
 * Once every pose is done, announce that analysis is starting and upload the
 * sharpest frames to /scan. */
export default function useAutoScan(precision = true) {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const framesRef = useRef([]);
  const timersRef = useRef({ cap: null, prog: null, countdown: null, segEnd: null });
  const segIndexRef = useRef(0);
  const segStartRef = useRef(0);

  const [region, setRegion] = useState("full");
  const [phase, setPhase] = useState("idle"); // idle | scanning | uploading
  const [progress, setProgress] = useState(0);
  const [count, setCount] = useState(0);
  const [guide, setGuide] = useState("");
  const [pose, setPose] = useState("front"); // current segment's guide shape for the alignment overlay
  const [countdown, setCountdown] = useState(null); // 3..1 while repositioning, null while capturing
  const [screenLight, setScreenLight] = useState(true);
  const [voiceOn, setVoiceOnState] = useState(true);
  const voiceOnRef = useRef(true);

  const params = REGION_PARAMS[region];
  const totalDurationS = params.duration + params.guides.length * POSE_COUNTDOWN_S;

  // Mirrored into a ref so the scan-loop's setInterval callback (a closure captured
  // once per `start()` call) always reads the latest toggle, not a stale one.
  const setVoiceOn = (value) => {
    setVoiceOnState((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      voiceOnRef.current = next;
      return next;
    });
  };

  const speak = (text) => {
    if (!voiceOnRef.current || !("speechSynthesis" in window)) return;
    try {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(text.replace(/[⟵⟶]/g, "").trim()));
    } catch (e) {}
  };

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const clearTimers = () => {
    const t = timersRef.current;
    clearInterval(t.cap); clearInterval(t.prog); clearTimeout(t.countdown); clearTimeout(t.segEnd);
    t.cap = t.prog = t.countdown = t.segEnd = null;
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
    fd.append("precision", precision ? "true" : "false");
    try {
      // /scan hands the actual analysis off to a background job and returns
      // right away -- Results polls the session until it's done, so there's
      // nothing to read off this response beyond the session to navigate to.
      const res = await api.post("/scan", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Photos captured — analyzing now.");
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
    segIndexRef.current = 0;
    setCount(0); setProgress(0); setPhase("scanning");

    const canvas = document.createElement("canvas");
    const sharpCanvas = document.createElement("canvas");
    sharpCanvas.width = 96; sharpCanvas.height = 96;

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

    const sliceDurationMs = (params.duration * 1000) / params.guides.length;
    const segTotalMs = POSE_COUNTDOWN_S * 1000 + sliceDurationMs;

    const finishScan = () => {
      clearTimers();
      setCountdown(null);
      setProgress(100);
      stopStream();
      if (framesRef.current.length === 0) { toast.error("No frames captured"); setPhase("idle"); return; }
      speak("Analyzing all the photos, please wait.");
      uploadFrames();
    };

    const beginCapture = (segIndex, poseKey) => {
      const captureOnce = () => {
        const v = videoRef.current;
        if (!v || !v.videoWidth) return;
        const sharp = sharpness();
        canvas.width = v.videoWidth; canvas.height = v.videoHeight;
        canvas.getContext("2d").drawImage(v, 0, 0);
        canvas.toBlob((b) => { if (b) { framesRef.current.push({ blob: b, region: poseKey, sharp }); setCount(framesRef.current.length); } }, "image/jpeg", 0.9);
      };
      captureOnce();
      timersRef.current.cap = setInterval(captureOnce, params.interval);
      timersRef.current.segEnd = setTimeout(() => {
        clearInterval(timersRef.current.cap); timersRef.current.cap = null;
        runSegment(segIndex + 1);
      }, sliceDurationMs);
    };

    const startCountdown = (onDone) => {
      let n = POSE_COUNTDOWN_S;
      setCountdown(n);
      const tick = () => {
        n -= 1;
        if (n > 0) {
          setCountdown(n);
          timersRef.current.countdown = setTimeout(tick, 1000);
        } else {
          setCountdown(null);
          onDone();
        }
      };
      timersRef.current.countdown = setTimeout(tick, 1000);
    };

    const runSegment = (segIndex) => {
      if (segIndex >= params.guides.length) { finishScan(); return; }
      segIndexRef.current = segIndex;
      segStartRef.current = Date.now();
      const guideText = params.guides[segIndex];
      const poseKey = params.regionMap ? params.regionMap[segIndex] : region;
      setGuide(guideText);
      setPose(poseKey);
      speak(guideText);
      startCountdown(() => beginCapture(segIndex, poseKey));
    };

    timersRef.current.prog = setInterval(() => {
      const el = Date.now() - segStartRef.current;
      const segFrac = Math.min(1, el / segTotalMs);
      setProgress(Math.min(100, ((segIndexRef.current + segFrac) / params.guides.length) * 100));
    }, 200);

    runSegment(0);
  };

  const cancel = () => {
    clearTimers(); stopStream();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    framesRef.current = []; setCount(0); setProgress(0); setCountdown(null); setPhase("idle");
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

  useEffect(() => () => {
    clearTimers(); stopStream();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }, []);

  return {
    videoRef, region, setRegion, phase, progress, count, guide, pose, countdown, params, totalDurationS, start, cancel,
    screenLight, setScreenLight, voiceOn, setVoiceOn,
  };
}
