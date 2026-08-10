import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { Download, Activity, Loader2 } from "lucide-react";
import MetricDelta from "@/components/MetricDelta";

const fetchProgress = async () => (await api.get("/progress")).data;
const fetchTimeline = async () => (await api.get("/timeline")).data;

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
                    <p className="font-heading text-3xl font-bold">{val ?? "—"}</p>
                    <MetricDelta current={val} baseline={base} testId={`report-delta-${label.toLowerCase()}`} />
                  </div>
                ))}
              </div>

              {/* Side by side */}
              {detail?.baseline_best_image && detail?.current_best_image && (
                <div className="grid grid-cols-2 gap-4 mb-8">
                  <figure><div className="rounded-2xl overflow-hidden border border-border"><img src={fileUrl(detail.baseline_best_image)} alt="baseline" className="w-full aspect-square object-cover" /></div><figcaption className="text-center text-xs text-muted-foreground mt-2 uppercase tracking-[0.15em]">Baseline</figcaption></figure>
                  <figure><div className="rounded-2xl overflow-hidden border border-primary/40"><img src={fileUrl(detail.current_best_image)} alt="current" className="w-full aspect-square object-cover" /></div><figcaption className="text-center text-xs text-primary mt-2 uppercase tracking-[0.15em]">Latest</figcaption></figure>
                </div>
              )}

              {/* Trend */}
              {points.length > 1 && (
                <div className="mb-8">
                  <h3 className="font-heading font-semibold mb-3">Trend over time</h3>
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
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* AI summary */}
              {a?.ai_summary && (
                <div className="rounded-2xl bg-secondary/50 border border-border p-5 mb-6">
                  <h3 className="font-heading font-semibold mb-2">Latest insight</h3>
                  <p className="text-sm leading-relaxed">{a.ai_summary}</p>
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
