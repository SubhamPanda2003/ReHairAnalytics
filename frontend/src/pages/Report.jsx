import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, fileUrl } from "@/lib/api";
import { fmtScore, hasScore } from "@/lib/scores";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { Download, Activity, Loader2 } from "lucide-react";
import MetricDelta from "@/components/MetricDelta";
import TrendBadge from "@/components/TrendBadge";
import ChangeMaps from "@/components/ChangeMaps";
import ExperimentalDensity from "@/components/ExperimentalDensity";
import ScalpMap from "@/components/ScalpMap";

const fetchProgress = async () => (await api.get("/progress")).data;
const fetchTimeline = async () => (await api.get("/timeline")).data;

const confidenceLabel = (c) => (!hasScore(c) ? null : c >= 80 ? "High" : c >= 60 ? "Moderate" : "Low");

// Auto-scan frames carry a `region` (front/left/right/crown/hairline/back); manual uploads
// carry a `view` (front/top/left/right/back) instead. Either way, group by whichever is present.
const REGION_ORDER = ["front", "left", "right", "crown", "hairline", "back", "top"];

// Best photo per region/view for a day's session -- same ranking the backend uses for
// baseline/current (highest confidence, then quality) -- capped at 6.
const bestPerRegion = (images) => {
  if (!images || images.length === 0) return [];
  const best = {};
  for (const img of images) {
    const key = img.region || img.view || "photo";
    const current = best[key];
    const better = !current
      || (img.confidence || 0) > (current.confidence || 0)
      || ((img.confidence || 0) === (current.confidence || 0) && (img.quality_score || 0) > (current.quality_score || 0));
    if (better) best[key] = img;
  }
  return Object.entries(best)
    .sort(([a], [b]) => {
      const ai = REGION_ORDER.indexOf(a), bi = REGION_ORDER.indexOf(b);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    })
    .slice(0, 6)
    .map(([, img]) => img);
};

export default function Report() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data: progress, isLoading } = useQuery({ queryKey: ["progress"], queryFn: fetchProgress });
  const { data: timeline } = useQuery({ queryKey: ["timeline"], queryFn: fetchTimeline });

  const latestSession = timeline?.[timeline.length - 1];
  const { data: detail } = useQuery({
    queryKey: ["session", latestSession?.id],
    queryFn: async () => (await api.get(`/sessions/${latestSession.id}`)).data,
    enabled: !!latestSession?.id,
  });

  if (isLoading) return <div className="min-h-screen bg-background"><Navbar /><div className="flex justify-center py-24"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div></div>;

  const points = progress?.points || [];
  const latest = progress?.latest;
  const baseline = progress?.baseline;
  const a = detail?.analysis;

  return (
    <div className="min-h-screen bg-background" data-testid="report-page">
      <div className="no-print"><Navbar /></div>
      <main className="max-w-4xl mx-auto px-5 md:px-8 py-8">
        <div className="flex items-center justify-between mb-6 no-print">
          <h1 className="font-heading text-3xl font-bold tracking-tight">Progress report</h1>
          <Button onClick={() => window.print()} className="rounded-full" data-testid="download-report-btn"><Download className="w-4 h-4 mr-1.5" /> Download</Button>
        </div>

        <div id="report-sheet" className="rounded-3xl border border-border bg-card p-8 md:p-10">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border pb-6 mb-6">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center"><Activity className="w-5 h-5 text-primary-foreground" /></div>
              <div>
                <p className="font-heading font-bold">ReHairAnalytics</p>
                <p className="text-xs text-muted-foreground">Objective hair tracking report</p>
              </div>
            </div>
            <div className="text-right text-sm">
              <p className="font-medium">{user?.name}</p>
              <p className="text-muted-foreground text-xs">{new Date().toLocaleDateString()}</p>
            </div>
          </div>

          {points.length === 0 ? (
            <p className="text-muted-foreground text-center py-10">No scans yet. Complete a scan to generate your report.</p>
          ) : (
            <>
              {/* Latest metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
                {[
                  ["Density", latest?.density, baseline?.density],
                  ["Coverage", latest?.coverage, baseline?.coverage],
                  ["Hairline", latest?.hairline, baseline?.hairline],
                  ["Overall", latest?.overall, baseline?.overall],
                ].map(([label, val, base]) => (
                  <div key={label} className="rounded-2xl border border-border p-4">
                    <p className="text-xs uppercase tracking-[0.15em] text-muted-foreground">{label}</p>
                    <p className="font-heading text-3xl font-bold">{fmtScore(val)}</p>
                    <MetricDelta current={val} baseline={base} testId={`report-delta-${label.toLowerCase()}`} noiseFloor={progress?.noise_floor} />
                  </div>
                ))}
              </div>
              {progress?.noise_floor != null && (
                <p className="text-[11px] text-muted-foreground -mt-6 mb-8">
                  Based on repeat AI readings of this week's photos, changes smaller than ±{progress.noise_floor} points are within normal measurement variation, not confirmed change.
                </p>
              )}

              {/* Measurement quality */}
              {a && (
                <div className="rounded-2xl border border-border p-4 mb-8 flex flex-wrap items-center gap-x-6 gap-y-1.5 text-xs" data-testid="report-measurement-quality">
                  <span className="text-muted-foreground uppercase tracking-[0.1em] font-semibold">Measurement quality</span>
                  <span>Confidence <b className="text-foreground">{fmtScore(a.confidence, "%")}</b>{confidenceLabel(a.confidence) && <span className="text-muted-foreground"> ({confidenceLabel(a.confidence)})</span>}</span>
                  <span>Photo quality <b className="text-foreground">{fmtScore(a.quality_score)}</b></span>
                  <span>Visible scalp <b className="text-foreground">{fmtScore(a.visible_scalp_pct, "%")}</b></span>
                </div>
              )}

              {/* Side by side */}
              {detail?.baseline_best_image && detail?.current_best_image && (
                <div className="mb-8">
                  {detail.photo_comparison_region_matched === false && (
                    <p className="text-xs text-amber-600 dark:text-amber-500 bg-amber-500/10 rounded-xl px-3 py-2 mb-3">
                      Baseline and latest don't share a captured region in common, so these photos may show different parts of your scalp.
                    </p>
                  )}
                  <div className="grid grid-cols-2 gap-4">
                    <figure><div className="rounded-2xl overflow-hidden border border-border"><img src={fileUrl(detail.baseline_best_image)} alt="baseline" className="w-full aspect-square object-cover" /></div><figcaption className="text-center text-xs text-muted-foreground mt-2 uppercase tracking-[0.15em]">Baseline</figcaption></figure>
                    <figure><div className="rounded-2xl overflow-hidden border border-primary/40"><img src={fileUrl(detail.current_best_image)} alt="current" className="w-full aspect-square object-cover" /></div><figcaption className="text-center text-xs text-primary mt-2 uppercase tracking-[0.15em]">Latest</figcaption></figure>
                  </div>
                </div>
              )}

              {/* Visual change map */}
              <ChangeMaps sessionId={latestSession?.id} testId="report-change-maps" />

              {/* Scalp visibility map (color-based patch highlight, per region) */}
              <ScalpMap perRegion={a?.per_region} testId="report-scalp-map" />

              {/* Hair density estimate -- shown expanded since a printed report has no toggle to click */}
              <ExperimentalDensity estimate={a?.density_estimate} testId="report-density" defaultOpen />

              {/* Trend */}
              {points.length > 1 && (
                <div className="mb-8">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                    <h3 className="font-heading font-semibold">Trend over time</h3>
                    <TrendBadge trend={progress?.trend} testId="report-trend-badge" />
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">
                    "Overall (smoothed)" averages each point with the one before it, so a single noisy reading doesn't look like a real swing.
                    {progress?.trend?.direction && progress.trend.direction !== "insufficient_data" && (
                      " The badge above fits a line across every scan and only calls it a real trend once it clears normal measurement noise -- not just whether the last two points moved."
                    )}
                  </p>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={points} margin={{ left: -20, right: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }} />
                      <Legend />
                      <Line type="monotone" dataKey="density" stroke="hsl(var(--chart-1))" strokeWidth={2.5} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="coverage" stroke="hsl(var(--chart-2))" strokeWidth={2.5} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="hairline" stroke="hsl(var(--chart-3))" strokeWidth={2.5} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="overall_smoothed" name="Overall (smoothed)" stroke="hsl(var(--chart-4))" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 2 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Photo timeline */}
              {timeline && timeline.length > 0 && (
                <div className="mb-8">
                  <h3 className="font-heading font-semibold mb-1">Photo timeline</h3>
                  <p className="text-xs text-muted-foreground mb-4">Best photo per captured region for each scan (up to 6), alongside that scan's measurements.</p>
                  <div className="space-y-4">
                    {timeline.map((s) => {
                      const regionPhotos = bestPerRegion(s.images);
                      return (
                        <div key={s.id} className="rounded-2xl border border-border p-4" data-testid={`report-scan-${s.id}`}>
                          <div className="flex items-center justify-between mb-3">
                            <p className="text-sm font-semibold">
                              {new Date(s.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                              <span className="text-muted-foreground font-normal"> · {new Date(s.date).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</span>
                            </p>
                            <p className="text-xs text-muted-foreground">{s.analysis ? <>Overall <b className="text-foreground">{fmtScore(s.analysis.overall_score)}</b></> : "Not analyzed"}</p>
                          </div>
                          {regionPhotos.length === 0 ? (
                            <p className="text-xs text-muted-foreground">No photos</p>
                          ) : (
                            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                              {regionPhotos.map((img) => (
                                <figure key={img.id}>
                                  <div className="rounded-lg overflow-hidden border border-border aspect-square">
                                    <img src={fileUrl(img.thumb_path)} alt={img.region || img.view} className="w-full h-full object-cover" />
                                  </div>
                                  <figcaption className="text-[10px] text-center text-muted-foreground mt-1 capitalize">{img.region || img.view}</figcaption>
                                </figure>
                              ))}
                            </div>
                          )}
                          {((s.coach_corrections || []).length > 0 || (s.coach_notes || []).length > 0) && (
                            <div className="mt-3 pt-3 border-t border-border space-y-1.5">
                              {(s.coach_corrections || []).map((c) => (
                                <div key={c.id} className="rounded-lg bg-amber-500/10 px-3 py-1.5 text-xs capitalize" data-testid={`report-coach-correction-${c.id}`}>
                                  <span className="font-medium">{c.metric}:</span> AI said {c.ai_value ?? "—"} → coach says {c.corrected_value}
                                  {c.note && <span className="normal-case text-muted-foreground"> — {c.note}</span>}
                                </div>
                              ))}
                              {(s.coach_notes || []).map((n) => (
                                <div key={n.id} className="rounded-lg bg-secondary/40 px-3 py-1.5 text-xs" data-testid={`report-coach-note-${n.id}`}>
                                  <span className="font-medium">{n.coach_name || "Coach"}:</span> {n.text}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* AI summary */}
              {a?.ai_summary && (
                <div className="rounded-2xl bg-secondary/50 border border-border p-5 mb-6">
                  <h3 className="font-heading font-semibold mb-2">Latest insight</h3>
                  <p className="text-sm leading-relaxed">{a.ai_summary}</p>
                  {a?.region_insights && Object.keys(a.region_insights).length > 0 && (
                    <div className="mt-4 pt-4 border-t border-border space-y-2">
                      {Object.entries(a.region_insights).map(([reg, insight]) => (
                        <p key={reg} className="text-xs leading-relaxed" data-testid={`report-region-insight-${reg}`}>
                          <span className="capitalize font-semibold">{reg}: </span>
                          <span className="text-muted-foreground">{insight}</span>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <p className="text-[11px] text-muted-foreground border-t border-border pt-4">This report presents objective photographic measurements only. It does not diagnose hair loss or provide medical advice. Based on {progress?.streak} scan(s); latest averaged across all sharp frames captured (very blurry frames excluded).</p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
