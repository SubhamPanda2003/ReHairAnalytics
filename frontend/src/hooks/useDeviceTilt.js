import { useEffect, useRef, useState } from "react";

/** Live device-tilt reading from the phone's orientation sensor, for a "hold
 * level" nudge during capture -- rotation was found to be the single largest
 * measured source of AI-scoring noise (a 3-degree tilt alone swung a score
 * 30->65 in backend testing; see CAPTURE_NOISE_FLOOR's docstring).
 *
 * `gamma` (left-right roll) is the relevant axis for a phone held upright
 * for a selfie -- the same kind of rotation the noise-floor eval measured,
 * not beta (front-back pitch) or alpha (compass heading).
 *
 * MUST degrade invisibly when unsupported: no sensor API at all (most
 * desktop browsers), permission denied (iOS 13+ requires an explicit
 * user-gesture-triggered grant via DeviceOrientationEvent.requestPermission),
 * or a listener that's registered but never actually fires (some
 * device/browser combinations). Capture must never be blocked or degraded
 * by the absence of a gyroscope -- `supported` starts false and only flips
 * true once a REAL reading arrives; nothing here ever throws or blocks.
 *
 * @param {boolean} active - only listens while true (e.g. while the capture
 *   overlay is open); pass this from a state flip that itself originated
 *   from a user gesture (a click handler), since iOS's permission prompt
 *   requires that to succeed.
 */
export default function useDeviceTilt(active) {
  const [supported, setSupported] = useState(false);
  const [tilt, setTilt] = useState(0); // abs(gamma), degrees off level
  const gotEventRef = useRef(false);

  useEffect(() => {
    if (!active) {
      setSupported(false);
      return;
    }
    gotEventRef.current = false;
    if (typeof window === "undefined" || typeof window.DeviceOrientationEvent === "undefined") {
      return; // no sensor API in this browser at all -- indicator stays hidden
    }

    let cancelled = false;
    let timer = null;

    const onOrientation = (e) => {
      if (cancelled || e.gamma == null) return;
      gotEventRef.current = true;
      setSupported(true);
      setTilt(Math.abs(e.gamma));
    };

    const attach = () => {
      if (cancelled) return;
      window.addEventListener("deviceorientation", onOrientation);
      // Some browsers accept the listener but never actually fire it (no
      // motion sensor present) -- treat silence as unsupported rather than
      // leaving a dead indicator around.
      timer = setTimeout(() => {
        if (!cancelled && !gotEventRef.current) setSupported(false);
      }, 1500);
    };

    const requestFn = window.DeviceOrientationEvent.requestPermission;
    if (typeof requestFn === "function") {
      try {
        requestFn
          .call(window.DeviceOrientationEvent)
          .then((state) => { if (state === "granted") attach(); })
          .catch(() => {});
      } catch (e) {
        // Permission API present but throws synchronously -- treat as
        // unsupported, never let this break the capture flow.
      }
    } else {
      attach();
    }

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener("deviceorientation", onOrientation);
    };
  }, [active]);

  return { supported, tilt };
}
