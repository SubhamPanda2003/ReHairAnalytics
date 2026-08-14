import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FlaskConical, Loader2, ChevronDown, ChevronUp } from "lucide-react";

const REGION_LABELS = { front: "front", left: "left", right: "right", crown: "crown", hairline: "hairline", back: "back", top: "top" };

/**
 * Opt-in, collapsed-by-default experimental hairs/cm^2 reading. Kept out of
 * the printable Report and off by default in Results so an unvalidated
 * number never reads as an official measurement -- the user has to
 * explicitly ask to see it, and every render restates that it's a guess.
 *
 * This is a direct LLM visual guess (see ai_service.estimate_density_llm) --
 * there's no CV pipeline behind it anymore, so the number is only ever as
 * good as the model's own read of the photo. Its self-reported confidence
 * and reasoning are shown alongside the number rather than a bare figure.
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
          <span className="font-heading font-semibold text-lg">Hair Density Estimate (hairs/cm²)</span>
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />}
      </button>

      {open && (
        <div className="mt-4">
          <p className="text-xs text-muted-foreground mb-4">
            Not a clinical measurement. This is the AI's own rough visual guess at hair density from your photo —
            not a computed measurement — so treat it as a talking point, not a number to track precisely week to week.
          </p>

          {isLoading && (
            <div className="flex items-center justify-center py-8" data-testid={`${testId}-loading`}>
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {isError && (
            <p className="text-sm text-muted-foreground" data-testid={`${testId}-unavailable`}>
              {error?.response?.data?.detail || "Couldn't get a density guess from this session's photos."}
            </p>
          )}

          {data && (
            <div data-testid={`${testId}-result`}>
              <p className="text-[11px] text-muted-foreground mb-3">
                From the {REGION_LABELS[data.source_region] || data.source_region} photo.
              </p>
              <div className="flex items-baseline gap-2 mb-1">
                <span className="font-heading text-3xl font-bold">{data.hairs_per_cm2}</span>
                <span className="text-sm text-muted-foreground">hairs/cm²</span>
              </div>
              <p className="text-xs text-muted-foreground mb-2">
                AI's own confidence: {data.confidence}%
                {data.confidence < 50 && <span className="text-amber-600 dark:text-amber-500"> (low)</span>}.
              </p>
              {data.reasoning && <p className="text-xs text-muted-foreground italic">"{data.reasoning}"</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
