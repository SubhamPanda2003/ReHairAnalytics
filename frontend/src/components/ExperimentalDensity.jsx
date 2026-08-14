import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FlaskConical, Loader2, ChevronDown, ChevronUp } from "lucide-react";

const REGION_LABELS = { front: "front", left: "left", right: "right", crown: "crown", hairline: "hairline", back: "back", top: "top" };

/**
 * Opt-in, collapsed-by-default experimental hairs/cm^2 reading. Kept out of
 * the printable Report and off by default in Results so an unvalidated,
 * wide-margin number never reads as an official measurement -- the user has
 * to explicitly ask to see it, and every render restates the margin and the
 * method's real limitations.
 *
 * Shows TWO independent estimates side by side, never blended into one
 * number: a real CV-computed estimate (cv_estimate) and a separate LLM
 * visual guess (llm_estimate), each with its own confidence, so the two can
 * be compared rather than one masquerading as the other.
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

  const cv = data?.cv_estimate;
  const llm = data?.llm_estimate;

  return (
    <div className="rounded-3xl border border-dashed border-border bg-card/50 p-6 md:p-8 mb-6" data-testid={testId}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 text-left"
        data-testid={`${testId}-toggle`}
      >
        <span className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-muted-foreground" />
          <span className="font-heading font-semibold text-lg">Hair Density Estimate (hairs/cm²)</span>
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />}
      </button>

      {open && (
        <div className="mt-4">
          <p className="text-xs text-muted-foreground mb-4">
            Not a clinical measurement. Two independent readings below: one from real CV computation (face-based
            photo calibration + pixel color analysis) and one from the AI's own direct visual guess at the same
            photo. They're kept separate on purpose — compare them, don't average them — and both carry an honest
            confidence rather than a promise of accuracy.
          </p>

          {isLoading && (
            <div className="flex items-center justify-center py-8" data-testid={`${testId}-loading`}>
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {isError && (
            <p className="text-sm text-muted-foreground" data-testid={`${testId}-unavailable`}>
              {error?.response?.data?.detail || "Couldn't detect a face in any photo from this session — this needs a clear, forward-facing shot with both eyes visible."}
            </p>
          )}

          {data && (
            <div data-testid={`${testId}-result`} className="space-y-4">
              <p className="text-[11px] text-muted-foreground">
                From the {REGION_LABELS[data.source_region] || data.source_region} photo.
              </p>

              <div className="grid sm:grid-cols-2 gap-3">
                <div className="rounded-2xl border border-border p-4" data-testid={`${testId}-cv`}>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/80 mb-1">CV estimate</p>
                  <div className="flex items-baseline gap-2 mb-1">
                    <span className="font-heading text-2xl font-bold">{cv.hairs_per_cm2}</span>
                    <span className="text-xs text-muted-foreground">hairs/cm² (±{cv.margin_pct}%)</span>
                  </div>
                  <p className="text-xs text-muted-foreground mb-2">
                    Likely between <b className="text-foreground">{cv.low}</b>–<b className="text-foreground">{cv.high}</b>. Face-detection confidence: {Math.round(cv.confidence * 100)}%
                    {cv.confidence < 0.7 && <span className="text-amber-600 dark:text-amber-500"> (low — treat with extra caution)</span>}.
                  </p>
                  <div className="rounded-xl border border-border p-2.5 text-[11px] text-muted-foreground space-y-1">
                    <div className="flex justify-between"><span>Eye-distance calibration</span><span>±{cv.error_sources.eye_calibration}%</span></div>
                    <div className="flex justify-between"><span>Hair/scalp color segmentation</span><span>±{cv.error_sources.coverage_segmentation}%</span></div>
                    <div className="flex justify-between"><span>Assumed "full coverage" reference</span><span>±{cv.error_sources.reference_fraction_assumption}%</span></div>
                    <div className="flex justify-between"><span>Clinical reference population range</span><span>±{cv.error_sources.reference_density_population}%</span></div>
                  </div>
                  {cv.quality_flags?.length > 0 && (
                    <ul className="list-disc list-inside mt-2 text-[11px] text-muted-foreground space-y-0.5" data-testid={`${testId}-flags`}>
                      {cv.quality_flags.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  )}
                </div>

                <div className="rounded-2xl border border-border p-4" data-testid={`${testId}-llm`}>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/80 mb-1">AI visual guess</p>
                  {llm?.hairs_per_cm2 != null ? (
                    <>
                      <div className="flex items-baseline gap-2 mb-1">
                        <span className="font-heading text-2xl font-bold">{llm.hairs_per_cm2}</span>
                        <span className="text-xs text-muted-foreground">hairs/cm²</span>
                      </div>
                      <p className="text-xs text-muted-foreground mb-2">
                        AI's own confidence: {llm.confidence}%
                        {llm.confidence < 50 && <span className="text-amber-600 dark:text-amber-500"> (low)</span>}.
                      </p>
                      {llm.reasoning && <p className="text-[11px] text-muted-foreground italic">"{llm.reasoning}"</p>}
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground">AI estimate unavailable for this photo right now.</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
