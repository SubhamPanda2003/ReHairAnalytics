import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, fileUrl } from "@/lib/api";
import { fmtScore } from "@/lib/scores";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { Camera, ChevronRight, Loader2, ImageOff, Trash2, UserRound } from "lucide-react";
import TrendBadge from "@/components/TrendBadge";

const fetchTimeline = async () => (await api.get("/timeline")).data;
const fetchProgress = async () => (await api.get("/progress")).data;

export default function Timeline() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: timeline, isLoading } = useQuery({ queryKey: ["timeline"], queryFn: fetchTimeline });
  const { data: progress } = useQuery({ queryKey: ["progress"], queryFn: fetchProgress });
  const { data: coachInfo } = useQuery({ queryKey: ["my-coach"], queryFn: async () => (await api.get("/coach/mine")).data });
  const points = progress?.points || [];
  const [toDelete, setToDelete] = useState(null);

  const toggleCoachShare = async (share) => {
    try {
      await api.post("/coach/share", { share });
      qc.invalidateQueries({ queryKey: ["my-coach"] });
      toast.success(share ? "Now sharing your timeline with your coach" : "Sharing turned off");
    } catch (e) { toast.error("Could not update sharing"); }
  };

  const deleteSession = useMutation({
    mutationFn: (id) => api.delete(`/sessions/${id}`),
    onSuccess: () => {
      toast.success("Scan deleted");
      qc.invalidateQueries({ queryKey: ["timeline"] });
      qc.invalidateQueries({ queryKey: ["progress"] });
    },
    onError: (e) => toast.error(e.response?.data?.detail || "Could not delete this scan"),
  });

  // Baseline is an average of the earliest BASELINE_BLEND_N scans (see
  // services/sessions.py), not just the single oldest one -- timeline is sorted
  // oldest-first by the backend, same order used to pick which scans contribute.
  const BASELINE_BLEND_N = 3;
  const deleteIndex = toDelete ? (timeline || []).findIndex((s) => s.id === toDelete.id) : -1;
  const affectsBaseline = deleteIndex !== -1 && deleteIndex < BASELINE_BLEND_N;
  const remainingCount = (timeline?.length || 0) - (toDelete ? 1 : 0);

  return (
    <div className="min-h-screen bg-background" data-testid="timeline-page">
      <Navbar />
      <main className="max-w-5xl mx-auto px-5 md:px-8 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight">Timeline</h1>
            <p className="text-muted-foreground mt-1">Every scan is a milestone. Tap one to open its comparison.</p>
          </div>
          <Button onClick={() => navigate("/upload")} className="rounded-full h-11 px-6" data-testid="timeline-upload-btn"><Camera className="w-4 h-4 mr-1.5" /> New scan</Button>
        </div>

        {coachInfo?.coach && (
          <div className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 mb-6" data-testid="timeline-coach-share">
            <div className="flex items-center gap-2 text-sm min-w-0">
              <UserRound className="w-4 h-4 text-muted-foreground shrink-0" />
              <span className="truncate">Share this timeline with <b>{coachInfo.coach.name || "your coach"}</b></span>
            </div>
            <Switch checked={!!coachInfo.share_with_coach} onCheckedChange={toggleCoachShare} data-testid="timeline-coach-share-switch" />
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-20"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div>
        ) : (timeline?.length || 0) === 0 ? (
          <div className="rounded-2xl border border-border bg-card p-12 text-center">
            <ImageOff className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No milestones yet. Upload your baseline to begin.</p>
          </div>
        ) : (
          <>
            {points.length > 1 && (
              <div className="rounded-2xl border border-border bg-card p-6 mb-8" data-testid="timeline-chart">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                  <h3 className="font-heading font-semibold text-lg">All metrics over time</h3>
                  <TrendBadge trend={progress?.trend} testId="timeline-trend-badge" />
                </div>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={points} margin={{ left: -20, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }} />
                    <Legend />
                    <Line type="monotone" dataKey="density" stroke="hsl(var(--chart-1))" strokeWidth={2.5} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="coverage" stroke="hsl(var(--chart-2))" strokeWidth={2.5} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="hairline" stroke="hsl(var(--chart-3))" strokeWidth={2.5} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="quality" stroke="hsl(var(--chart-4))" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="relative pl-8">
              <div className="absolute left-3 top-2 bottom-2 w-px bg-border" />
              {[...timeline].reverse().map((s, i) => (
                <motion.div key={s.id} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                  className="relative mb-4 group">
                  <span className="absolute -left-[22px] top-6 w-3 h-3 rounded-full bg-primary ring-4 ring-background" />
                  <div className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4 hover:-translate-y-0.5 transition-transform duration-200">
                    <button onClick={() => navigate(`/results/${s.id}`)} data-testid={`timeline-milestone-${s.id}`}
                      className="flex items-center gap-4 flex-1 min-w-0 text-left">
                      {s.images?.[0] ? <img src={fileUrl(s.images[0].thumb_path)} alt="" className="w-16 h-16 rounded-xl object-cover" /> : <div className="w-16 h-16 rounded-xl bg-muted flex items-center justify-center"><ImageOff className="w-5 h-5 text-muted-foreground" /></div>}
                      <div className="flex-1 min-w-0">
                        <p className="font-heading font-semibold">
                          {new Date(s.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                          <span className="text-muted-foreground font-normal"> · {new Date(s.date).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</span>
                        </p>
                        <p className="text-xs text-muted-foreground">{s.region && s.region !== "full" ? `${s.region} focus · ` : ""}{s.images?.length || 0} photos</p>
                        {s.analysis ? (
                          <div className="flex gap-3 mt-1.5 text-xs">
                            <span>Density <b>{fmtScore(s.analysis.density_score)}</b></span>
                            <span>Coverage <b>{fmtScore(s.analysis.coverage_score)}</b></span>
                            <span>Overall <b>{fmtScore(s.analysis.overall_score)}</b></span>
                          </div>
                        ) : <p className="text-xs text-muted-foreground mt-1.5">Not analyzed</p>}
                      </div>
                    </button>
                    <button onClick={() => navigate(`/results/${s.id}`)} aria-label="Open scan" className="shrink-0">
                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-foreground transition-colors" />
                    </button>
                    <button
                      onClick={() => setToDelete(s)}
                      className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-muted-foreground hover:bg-destructive hover:text-destructive-foreground transition-colors duration-200"
                      aria-label={`Delete scan from ${new Date(s.date).toLocaleDateString()}`}
                      data-testid={`delete-scan-${s.id}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </motion.div>
              ))}
            </div>
          </>
        )}
      </main>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent className="rounded-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this scan?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes this scan and all its photos. This cannot be undone.
              {affectsBaseline && remainingCount > 0 && (
                <> Your baseline is averaged from your earliest scans — deleting this one will recalculate it from your {Math.min(BASELINE_BLEND_N, remainingCount)} remaining earliest scan{Math.min(BASELINE_BLEND_N, remainingCount) === 1 ? "" : "s"}.</>
              )}
              {affectsBaseline && remainingCount === 0 && (
                <> This is your only scan — deleting it clears your history.</>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-full" data-testid="delete-week-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { deleteSession.mutate(toDelete.id); setToDelete(null); }}
              className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="delete-week-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
