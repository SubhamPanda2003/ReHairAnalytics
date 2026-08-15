import { Radar } from "lucide-react";
import { fileUrl } from "@/lib/api";

const REGION_LABELS = { front: "Front", left: "Left", right: "Right", crown: "Crown", hairline: "Hairline", back: "Back", top: "Top" };
const REGION_ORDER = ["front", "left", "right", "crown", "hairline", "back", "top"];

/**
 * Per-region color-based scalp-patch highlight (see
 * image_utils.mark_scalp_patches) -- red marks areas color-clustering finds
 * scalp-colored rather than hair-colored, one image per captured region.
 * Computed once per scan (alongside the other per-region scores) and stored
 * on analysis.per_region[region].scalp_map_path, so this just renders
 * already-fetched data -- no API/CV call happens on render.
 */
export default function ScalpMap({ perRegion, testId = "scalp-map" }) {
  const entries = Object.entries(perRegion || {})
    .filter(([, m]) => m.scalp_map_path)
    .sort(([a], [b]) => REGION_ORDER.indexOf(a) - REGION_ORDER.indexOf(b));

  if (entries.length === 0) return null;

  return (
    <div className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-6" data-testid={testId}>
      <div className="flex items-center gap-2 mb-1"><Radar className="w-5 h-5 text-primary" /><h3 className="font-heading font-semibold text-lg">Scalp visibility map</h3></div>
      <p className="text-sm text-muted-foreground mb-4">
        Color analysis, not a clinical assessment — areas that look scalp-colored rather than hair-colored are marked red, per region.
        It can also catch skin or background that isn't scalp, and struggles with light or gray hair, so treat this as a rough visual aid.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {entries.map(([region, m]) => (
          <figure key={region} data-testid={`${testId}-${region}`}>
            <div className="rounded-2xl overflow-hidden border border-border">
              <img src={fileUrl(m.scalp_map_path)} alt={`${region} scalp map`} className="w-full aspect-square object-cover" />
            </div>
            <figcaption className="text-center text-xs text-muted-foreground mt-2 uppercase tracking-[0.15em]">{REGION_LABELS[region] || region}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}
