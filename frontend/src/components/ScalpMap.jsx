import { Radar } from "lucide-react";
import { fileUrl } from "@/lib/api";

/**
 * Crown-region color-based scalp-patch highlight (see
 * image_utils.mark_scalp_patches) -- red marks areas color-clustering finds
 * scalp-colored rather than hair-colored. Crown-only: it's the one region
 * this heuristic is actually tuned against, and other regions carry more of
 * its known failure modes (face/neck skin on "front", background on side
 * views) with no extra benefit -- the backend only ever generates a map for
 * analysis.per_region.crown, so this just renders whatever's there; no
 * API/CV call happens on render.
 */
export default function ScalpMap({ perRegion, testId = "scalp-map" }) {
  const path = perRegion?.crown?.scalp_map_path;
  if (!path) return null;

  return (
    <div className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-6" data-testid={testId}>
      <div className="flex items-center gap-2 mb-1"><Radar className="w-5 h-5 text-primary" /><h3 className="font-heading font-semibold text-lg">Scalp visibility map</h3></div>
      <p className="text-sm text-muted-foreground mb-4">
        Color analysis of your crown photo, not a clinical assessment — areas that look scalp-colored rather than hair-colored are marked red.
        It can also catch skin or background that isn't scalp, and struggles with light or gray hair, so treat this as a rough visual aid.
      </p>
      <div className="rounded-2xl overflow-hidden border border-border max-w-xs">
        <img src={fileUrl(path)} alt="Crown scalp map" className="w-full aspect-square object-cover" data-testid={`${testId}-crown`} />
      </div>
    </div>
  );
}
