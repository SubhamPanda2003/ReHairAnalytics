import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, fileUrl } from "@/lib/api";
import Navbar from "@/components/Navbar";
import ScoreRing from "@/components/ScoreRing";
import MetricDelta from "@/components/MetricDelta";
import ChangeMaps from "@/components/ChangeMaps";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { ArrowLeft, Sparkles, TrendingUp, TrendingDown, Minus, Loader2, FileText, Target, Trash2 } from "lucide-react";

const fetchSession = async (id) => (await api.get(`/sessions/${id}`)).data;

const Delta = ({ label, cur, ref }) => {
  if (ref === null || ref === undefined) return null;
  const d = Math.round((cur - ref) * 10) / 10;
  const Icon = d > 0 ? TrendingUp : d < 0 ? TrendingDown : Minus;
  const cls = d > 0 ? "text-primary" : d < 0 ? "text-destructive" : "text-muted-foreground";
  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={`text-sm font-semibold flex items-center gap-1 ${cls}`}><Icon className="w-3.5 h-3.5" />{d > 0 ? "+" : ""}{d}</span>
    </div>
  );
};

const ComparisonCard = ({ title, ref, a }) => {
  if (!ref) return (
    <div className="rounded-2xl border border-border bg-card p-6">
      <h3 className="font-heading font-semibold mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground">No comparison available yet.</p>
    </div>
  );
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid={`comparison-${title.toLowerCase().replace(/\s/g, "-")}`}>
      <h3 className="font-heading font-semibold mb-3">{title}</h3>
      <Delta label="Density" cur={a.density_score} ref={ref.density_score} />
      <Delta label="Coverage" cur={a.coverage_score} ref={ref.coverage_score} />
      <Delta label="Hairline" cur={a.hairline_score} ref={ref.hairline_score} />
      <Delta label="Overall" cur={a.overall_score} ref={ref.overall_score} />
    </div>
  );
};

export default function Results() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: s, isLoading } = useQuery({ queryKey: ["session", sessionId], queryFn: () => fetchSession(sessionId) });
  const [toDelete, setToDelete] = useState(null);

  const deleteImage = useMutation({
    mutationFn: (imageId) => api.delete(`/images/${imageId}`),
    onSuccess: () => {
      toast.success("Photo deleted");
      qc.invalidateQueries({ queryKey: ["session", sessionId] });
      qc.invalidateQueries({ queryKey: ["timeline"] });
    },
    onError: (e) => toast.error(e.response?.data?.detail || "Could not delete photo"),
  });

  if (isLoading) return <div className="min-h-screen bg-background"><Navbar /><div className="flex justify-center py-24"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div></div>;

  const a = s?.analysis;

  return (
    <div className="min-h-screen bg-background" data-testid="results-page">
      <Navbar />
      <main className="max-w-6xl mx-auto px-5 md:px-8 py-8">
        <Button variant="ghost" onClick={() => navigate(-1)} className="rounded-full mb-4" data-testid="results-back"><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
        <div className="flex flex-wrap items-end justify-between gap-3 mb-8">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{s?.date ? new Date(s.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : `Week ${s?.week_number}`}</p>
            <h1 className="font-heading text-3xl font-bold tracking-tight">Scan results</h1>
          </div>
          <div className="flex items-center gap-2">
            {a?.region && a.region !== "full" && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-semibold capitalize" data-testid="region-badge"><Target className="w-3.5 h-3.5" /> {a.region} focus</span>
            )}
            <Button variant="outline" className="rounded-full" onClick={() => navigate("/report")} data-testid="results-report-btn"><FileText className="w-4 h-4 mr-1.5" /> Report</Button>
          </div>
        </div>

        {!a ? (
          <div className="rounded-2xl border border-border bg-card p-10 text-center">
            <p className="text-muted-foreground">This scan hasn't been analyzed yet.</p>
          </div>
        ) : (
          <>
            {/* Scores */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6 justify-items-center">
                <div className="flex flex-col items-center">
                  <ScoreRing value={a.density_score} label="Density" color="hsl(var(--chart-1))" testId="ring-density" />
                  <MetricDelta current={a.density_score} baseline={s.baseline_analysis?.density_score} testId="delta-density" />
                </div>
                <div className="flex flex-col items-center">
                  <ScoreRing value={a.coverage_score} label="Coverage" color="hsl(var(--chart-2))" testId="ring-coverage" />
                  <MetricDelta current={a.coverage_score} baseline={s.baseline_analysis?.coverage_score} testId="delta-coverage" />
                </div>
                <div className="flex flex-col items-center">
                  <ScoreRing value={a.hairline_score} label="Hairline" color="hsl(var(--chart-3))" testId="ring-hairline" />
                  <MetricDelta current={a.hairline_score} baseline={s.baseline_analysis?.hairline_score} testId="delta-hairline" />
                </div>
                <div className="flex flex-col items-center">
                  <ScoreRing value={a.overall_score} label="Overall" color="hsl(var(--chart-4))" testId="ring-overall" />
                  <MetricDelta current={a.overall_score} baseline={s.baseline_analysis?.overall_score} testId="delta-overall" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 mt-8 text-center">
                <div><p className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Image quality</p><p className="font-heading text-2xl font-bold">{a.quality_score}</p></div>
                <div><p className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Confidence</p><p className="font-heading text-2xl font-bold">{a.confidence}%</p></div>
                <div><p className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Visible scalp</p><p className="font-heading text-2xl font-bold">{a.visible_scalp_pct}%</p></div>
              </div>
            </motion.div>

            {/* Per-region breakdown */}
            {a.per_region && Object.keys(a.per_region).length > 1 && (
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
                className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-6" data-testid="per-region">
                <h3 className="font-heading font-semibold text-lg mb-1">Per-region breakdown</h3>
                <p className="text-sm text-muted-foreground mb-4">Best photo picked from each area of your scalp.</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {Object.entries(a.per_region).map(([reg, m]) => (
                    <div key={reg} className="rounded-2xl border border-border p-4" data-testid={`region-metric-${reg}`}>
                      <p className="capitalize font-heading font-semibold">{reg}</p>
                      <div className="text-xs text-muted-foreground mt-2 space-y-1.5">
                        <div className="flex justify-between">Density <b className="text-foreground">{m.density_score}</b></div>
                        <div className="flex justify-between">Coverage <b className="text-foreground">{m.coverage_score}</b></div>
                        <div className="flex justify-between">Hairline <b className="text-foreground">{m.hairline_score}</b></div>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {/* AI summary */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
              className="rounded-3xl border border-primary/30 bg-card p-6 md:p-8 mb-6" data-testid="ai-summary">
              <div className="flex items-center gap-2 mb-3"><Sparkles className="w-5 h-5 text-primary" /><h3 className="font-heading font-semibold text-lg">AI insight</h3></div>
              <p className="text-base leading-relaxed text-foreground/90">{a.ai_summary}</p>
            </motion.div>

            {/* Side-by-side comparison */}
            {s.baseline_best_image && s.current_best_image && (
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
                className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-6" data-testid="side-by-side">
                <h3 className="font-heading font-semibold text-lg mb-4">Baseline vs current</h3>
                <div className="grid grid-cols-2 gap-4">
                  <figure>
                    <div className="rounded-2xl overflow-hidden border border-border">
                      <img src={fileUrl(s.baseline_best_image)} alt="baseline" className="w-full aspect-square object-cover" />
                    </div>
                    <figcaption className="text-center text-xs text-muted-foreground mt-2 uppercase tracking-[0.15em]">Baseline</figcaption>
                  </figure>
                  <figure>
                    <div className="rounded-2xl overflow-hidden border border-primary/40">
                      <img src={fileUrl(s.current_best_image)} alt="current" className="w-full aspect-square object-cover" />
                    </div>
                    <figcaption className="text-center text-xs text-primary mt-2 uppercase tracking-[0.15em]">This scan</figcaption>
                  </figure>
                </div>
              </motion.div>
            )}

            {/* Visual change map */}
            <ChangeMaps sessionId={sessionId} testId="change-maps" />

            {/* Comparisons */}
            <div className="grid md:grid-cols-2 gap-6 mb-6">
              <ComparisonCard title="vs Previous" ref={s.previous_analysis} a={a} />
              <ComparisonCard title="vs Baseline" ref={s.baseline_analysis} a={a} />
            </div>

            {/* Images */}
            <div className="rounded-2xl border border-border bg-card p-6" data-testid="results-gallery">
              <h3 className="font-heading font-semibold mb-4">Captured views</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                {s.images?.map((img) => (
                  <div key={img.id} className="relative rounded-xl overflow-hidden border border-border" data-testid={`gallery-image-${img.id}`}>
                    <img src={fileUrl(img.thumb_path)} alt={img.view} className="w-full aspect-square object-cover" />
                    <button
                      onClick={() => setToDelete(img)}
                      className="absolute top-1.5 right-1.5 w-7 h-7 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-destructive transition-colors duration-200"
                      aria-label={`Delete ${img.view} photo`}
                      data-testid={`delete-image-${img.id}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <p className="text-xs text-center py-1.5 capitalize text-muted-foreground">{img.view} · Q{img.quality_score}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </main>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent className="rounded-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this photo?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the {toDelete?.view} photo from this scan. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-full" data-testid="delete-image-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { deleteImage.mutate(toDelete.id); setToDelete(null); }}
              className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="delete-image-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
