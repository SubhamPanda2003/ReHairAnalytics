import { useQuery } from "@tanstack/react-query";
import { api, fileUrl } from "@/lib/api";
import { Layers, Loader2 } from "lucide-react";

const REGION_LABELS = { front: "Front", left: "Left", right: "Right", crown: "Crown", hairline: "Hairline", back: "Back", top: "Top" };

/** Baseline-vs-latest visual change map, one per matching captured region.
 * Renders nothing if there's no baseline yet or no region overlap -- safe to
 * drop in anywhere without its own gating condition. */
export default function ChangeMaps({ sessionId, testId = "change-maps" }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["change-maps", sessionId],
    queryFn: async () => (await api.get(`/sessions/${sessionId}/change-maps`)).data,
    enabled: !!sessionId,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-6 flex items-center justify-center py-16" data-testid={`${testId}-loading`}>
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  const maps = data?.maps || [];
  if (isError || maps.length === 0) return null;

  return (
    <div className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-6" data-testid={testId}>
      <div className="flex items-center gap-2 mb-1"><Layers className="w-5 h-5 text-primary" /><h3 className="font-heading font-semibold text-lg">Visual change map</h3></div>
      <p className="text-sm text-muted-foreground mb-4">
        Baseline vs. latest photo per region, pixel-aligned and compared. Warmer colors show where the image visibly changed — this maps visible change, not hair count or density.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {maps.map((m) => (
          <figure key={m.region} data-testid={`change-map-${m.region}`}>
            <div className="rounded-2xl overflow-hidden border border-border">
              <img src={fileUrl(m.heatmap_path)} alt={`${m.region} change map`} className="w-full aspect-square object-cover" />
            </div>
            <figcaption className="text-center text-xs text-muted-foreground mt-1.5 capitalize">
              {REGION_LABELS[m.region] || m.region}
              {!m.aligned && <span className="block text-[10px] normal-case">approximate — couldn't align precisely</span>}
            </figcaption>
          </figure>
        ))}
      </div>
      <div className="flex items-center justify-center gap-3 mt-4 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: "#2166ac" }} /> Little change</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: "#d7191c" }} /> More change</span>
      </div>
    </div>
  );
}
