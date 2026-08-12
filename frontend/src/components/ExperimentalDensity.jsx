import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FlaskConical, Loader2, ChevronDown, ChevronUp } from "lucide-react";

const REGION_LABELS = { front: "front", left: "left", right: "right", crown: "crown", hairline: "hairline", back: "back", top: "top" };

/**
 * Opt-in, collapsed-by-default experimental hairs/cm^2 estimate. Kept out of
 * the printable Report and off by default in Results so an unvalidated,
 * wide-margin number never reads as an official measurement -- the user has
 * to explicitly ask to see it, and every render restates the margin and the
 * method's real limitations.
 */
export default function ExperimentalDensity({ sessionId, testId = "experimental-density" }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["density-estimate", sessionId],
    queryFn: async () => (await api.get(`/sessions/${sessionId}/density-estimate`)).data,
    enabled: !!sessionId && open,
    retry: false,
  });

  if (!sessionId) return null;

  return (
    <div className="rounded-3xl border border-dashed border-border bg-card/50 p-6 md:p-8 mb-6" data-testid={testId}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 text-left"
        data-testid={`${testId}-toggle`}
      >
        <span className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-muted-foreground" />
          <span className="font-heading font-semibold text-lg">Experimental: estimated hair density (hairs/cm²)</span>
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />}
      </button>

      {open && (
        <div className="mt-4">
          <p className="text-xs text-muted-foreground mb-4">
            Not a clinical measurement. This uses real OpenCV computation (face-based photo calibration + pixel color
            analysis), not an AI guess — but converting that into hairs/cm² relies on an unvalidated modeling
            assumption, since there's no reference object or dermatoscope involved. Treat the range below as the
            honest uncertainty, not the fine print.
          </p>

          {isLoading && (
            <div className="flex items-center justify-center py-8" data-testid={`${testId}-loading`}>
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {isError && (
            <p className="text-sm text-muted-foreground" data-testid={`${testId}-unavailable`}>
              {error?.response?.data?.detail || "Couldn't get a confident reading from this session's photos — this needs a clear, front-facing shot with both eyes visible."}
            </p>
          )}

          {data && (
            <div data-testid={`${testId}-result`}>
              <div className="flex items-baseline gap-2 mb-1">
                <span className="font-heading text-3xl font-bold">{data.hairs_per_cm2}</span>
                <span className="text-sm text-muted-foreground">hairs/cm² (±{data.margin_pct}%)</span>
              </div>
              <p className="text-xs text-muted-foreground mb-4">
                Likely somewhere between <b className="text-foreground">{data.low}</b> and <b className="text-foreground">{data.high}</b> hairs/cm² —
                estimated from the {REGION_LABELS[data.source_region] || data.source_region} photo, face-detection confidence {Math.round(data.calibration_confidence * 100)}%.
              </p>
              <div className="rounded-2xl border border-border p-3 text-[11px] text-muted-foreground space-y-1">
                <p className="font-semibold uppercase tracking-[0.1em] text-muted-foreground/80">Where the ±{data.margin_pct}% comes from</p>
                <div className="flex justify-between"><span>Eye-distance calibration</span><span>±{data.error_sources.eye_calibration}%</span></div>
                <div className="flex justify-between"><span>Hair/scalp color segmentation</span><span>±{data.error_sources.coverage_segmentation}%</span></div>
                <div className="flex justify-between"><span>Assumed "full coverage" reference</span><span>±{data.error_sources.reference_fraction_assumption}%</span></div>
                <div className="flex justify-between"><span>Clinical reference population range</span><span>±{data.error_sources.reference_density_population}%</span></div>
              </div>
              {data.quality_flags?.length > 0 && (
                <div className="mt-3 text-[11px] text-muted-foreground" data-testid={`${testId}-flags`}>
                  <p className="font-semibold uppercase tracking-[0.1em] text-muted-foreground/80 mb-1">Why this photo's margin moved</p>
                  <ul className="list-disc list-inside space-y-0.5">
                    {data.quality_flags.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
