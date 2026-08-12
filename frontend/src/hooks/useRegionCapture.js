import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { BURST_DURATION_S, BURST_INTERVAL_MS, BURST_KEEP } from "@/components/upload/constants";

/** Drives a burst-capture for ONE region: opens the selfie camera, grabs a
 * frame every BURST_INTERVAL_MS for BURST_DURATION_S, scores each frame's
 * sharpness locally (no network/AI call), and hands the sharpest BURST_KEEP
 * frame(s) back via onDone -- it does not upload or navigate itself, so a
 * parent can accumulate frames across multiple regions before submitting one
 * combined /scan call. */
export default function useRegionCapture(onDone) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const framesRef = useRef([]);
  const timersRef = useRef({ cap: null, prog: null, final: null });
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const [phase, setPhase] = useState("idle"); // idle | scanning | done
  const [progress, setProgress] = useState(0);
  const [count, setCount] = useState(0);
  const [screenLight, setScreenLight] = useState(true);
  const [voiceOn, setVoiceOnState] = useState(true);
  const voiceOnRef = useRef(true);

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
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    } catch (e) {}
  };

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const clearTimers = () => {
    const t = timersRef.current;
    clearInterval(t.cap); clearInterval(t.prog); clearTimeout(t.final);
    t.cap = t.prog = t.final = null;
  };

  const finish = () => {
    clearTimers(); setProgress(100); stopStream();
    const frames = framesRef.current;
    if (frames.length === 0) {
      toast.error("No frames captured");
      setPhase("idle");
      return;
    }
    const kept = [...frames].sort((a, b) => b.sharp - a.sharp).slice(0, BURST_KEEP);
    setPhase("done");
    onDoneRef.current?.(kept);
  };

  const start = async (region, guide) => {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 1280, height: 1280 } });
    } catch (e) {
      toast.error(e?.name === "NotAllowedError" ? "Camera permission denied. Allow access or use the file option." : "Camera unavailable. Use the file option instead.");
      return;
    }
    streamRef.current = stream;
    framesRef.current = [];
    setCount(0); setProgress(0); setPhase("scanning");
    speak(guide);

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
      const sharp = sharpness();
      canvas.width = v.videoWidth; canvas.height = v.videoHeight;
      canvas.getContext("2d").drawImage(v, 0, 0);
      canvas.toBlob((b) => { if (b) { framesRef.current.push({ blob: b, region, sharp }); setCount(framesRef.current.length); } }, "image/jpeg", 0.9);
    };

    timersRef.current.cap = setInterval(capture, BURST_INTERVAL_MS);
    setTimeout(capture, 400);
    timersRef.current.prog = setInterval(() => {
      const el = (Date.now() - started) / 1000;
      setProgress(Math.min(100, (el / BURST_DURATION_S) * 100));
    }, 200);
    timersRef.current.final = setTimeout(finish, BURST_DURATION_S * 1000);
  };

  const cancel = () => {
    clearTimers(); stopStream();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    framesRef.current = []; setCount(0); setProgress(0); setPhase("idle");
  };

  const reset = () => setPhase("idle");

  useEffect(() => {
    if (phase === "scanning" && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [phase]);

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
    videoRef, phase, progress, count, start, cancel, reset,
    screenLight, setScreenLight, voiceOn, setVoiceOn,
  };
}
