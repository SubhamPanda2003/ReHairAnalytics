import React from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, fileUrl } from "@/lib/api";
import Navbar from "@/components/Navbar";
import ScoreRing from "@/components/ScoreRing";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Sparkles, TrendingUp, TrendingDown, Minus, ShieldCheck, Loader2 } from "lucide-react";

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
  const { data: s, isLoading } = useQuery({ queryKey: ["session", sessionId], queryFn: () => fetchSession(sessionId) });

  if (isLoading) return <div className="min-h-screen bg-background"><Navbar /><div className="flex justify-center py-24"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div></div>;

  const a = s?.analysis;

  return (
    <div className="min-h-screen bg-background" data-testid="results-page">
      <Navbar />
      <main className="max-w-6xl mx-auto px-5 md:px-8 py-8">
        <Button variant="ghost" onClick={() => navigate(-1)} className="rounded-full mb-4" data-testid="results-back"><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
        <div className="flex flex-wrap items-end justify-between gap-3 mb-8">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Week {s?.week_number}</p>
            <h1 className="font-heading text-3xl font-bold tracking-tight">Scan results</h1>
          </div>
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold">
            <ShieldCheck className="w-3.5 h-3.5" /> Objective measurement · not a diagnosis
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
                <div className="flex flex-col items-center"><ScoreRing value={a.density_score} label="Density" color="hsl(var(--chart-1))" testId="ring-density" /></div>
                <div className="flex flex-col items-center"><ScoreRing value={a.coverage_score} label="Coverage" color="hsl(var(--chart-2))" testId="ring-coverage" /></div>
                <div className="flex flex-col items-center"><ScoreRing value={a.hairline_score} label="Hairline" color="hsl(var(--chart-3))" testId="ring-hairline" /></div>
                <div className="flex flex-col items-center"><ScoreRing value={a.overall_score} label="Overall" color="hsl(var(--chart-4))" testId="ring-overall" /></div>
              </div>
              <div className="grid grid-cols-3 gap-4 mt-8 text-center">
                <div><p className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Image quality</p><p className="font-heading text-2xl font-bold">{a.quality_score}</p></div>
                <div><p className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Confidence</p><p className="font-heading text-2xl font-bold">{a.confidence}%</p></div>
                <div><p className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Visible scalp</p><p className="font-heading text-2xl font-bold">{a.visible_scalp_pct}%</p></div>
              </div>
            </motion.div>

            {/* AI summary */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
              className="rounded-3xl border border-primary/30 bg-card p-6 md:p-8 mb-6" data-testid="ai-summary">
              <div className="flex items-center gap-2 mb-3"><Sparkles className="w-5 h-5 text-primary" /><h3 className="font-heading font-semibold text-lg">AI insight</h3></div>
              <p className="text-base leading-relaxed text-foreground/90">{a.ai_summary}</p>
            </motion.div>

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
                  <div key={img.id} className="rounded-xl overflow-hidden border border-border">
                    <img src={fileUrl(img.thumb_path)} alt={img.view} className="w-full aspect-square object-cover" />
                    <p className="text-xs text-center py-1.5 capitalize text-muted-foreground">{img.view} · Q{img.quality_score}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
