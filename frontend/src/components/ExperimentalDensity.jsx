import { useState } from "react";
import { FlaskConical, ChevronDown, ChevronUp } from "lucide-react";

const REGION_LABELS = { front: "front", left: "left", right: "right", crown: "crown", hairline: "hairline", back: "back", top: "top" };

/**
 * Opt-in hairs/cm^2 reading, collapsed by default in Results so an
 * unvalidated number never reads as an official measurement -- the user has
 * to explicitly ask to see it, and every render restates that it's a guess.
 * Report passes defaultOpen so it appears expanded there (a printed/
 * downloaded report has no way to click a toggle).
 *
 * This is a direct LLM visual guess (see ai_service.estimate_density_llm),
 * computed ONCE per scan at analysis time and stored on the analysis
 * document -- `estimate` is just `analysis.density_estimate`, passed down
 * from data the page already fetched. Expanding this panel does not call
 * the API or the LLM; there's nothing left to fetch here.
 */
export default function ExperimentalDensity({ estimate, testId = "experimental-density", defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);

  if (estimate === undefined) return null;

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

          {estimate ? (
            <div data-testid={`${testId}-result`}>
              <p className="text-[11px] text-muted-foreground mb-3">
                From the {REGION_LABELS[estimate.source_region] || estimate.source_region} photo.
              </p>
              <div className="flex items-baseline gap-2 mb-1">
                <span className="font-heading text-3xl font-bold">{estimate.hairs_per_cm2}</span>
                <span className="text-sm text-muted-foreground">hairs/cm²</span>
              </div>
              <p className="text-xs text-muted-foreground mb-2">
                AI's own confidence: {estimate.confidence}%
                {estimate.confidence < 50 && <span className="text-amber-600 dark:text-amber-500"> (low)</span>}.
              </p>
              {estimate.reasoning && <p className="text-xs text-muted-foreground italic">"{estimate.reasoning}"</p>}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground" data-testid={`${testId}-unavailable`}>
              Couldn't get a density guess from this scan's photos.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
