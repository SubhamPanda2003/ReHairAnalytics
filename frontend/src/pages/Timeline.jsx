import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, fileUrl } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { Camera, ChevronRight, Loader2, ImageOff } from "lucide-react";

const fetchTimeline = async () => (await api.get("/timeline")).data;
const fetchProgress = async () => (await api.get("/progress")).data;

export default function Timeline() {
  const navigate = useNavigate();
  const { data: timeline, isLoading } = useQuery({ queryKey: ["timeline"], queryFn: fetchTimeline });
  const { data: progress } = useQuery({ queryKey: ["progress"], queryFn: fetchProgress });
  const points = progress?.points || [];

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
                <h3 className="font-heading font-semibold text-lg mb-4">All metrics over time</h3>
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
                <motion.button key={s.id} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                  onClick={() => navigate(`/results/${s.id}`)} data-testid={`timeline-milestone-${s.week_number}`}
                  className="relative w-full text-left mb-4 group">
                  <span className="absolute -left-[22px] top-6 w-3 h-3 rounded-full bg-primary ring-4 ring-background" />
                  <div className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4 hover:-translate-y-0.5 transition-transform duration-200">
                    {s.images?.[0] ? <img src={fileUrl(s.images[0].thumb_path)} alt="" className="w-16 h-16 rounded-xl object-cover" /> : <div className="w-16 h-16 rounded-xl bg-muted flex items-center justify-center"><ImageOff className="w-5 h-5 text-muted-foreground" /></div>}
                    <div className="flex-1 min-w-0">
                      <p className="font-heading font-semibold">{new Date(s.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</p>
                      <p className="text-xs text-muted-foreground">{s.region && s.region !== "full" ? `${s.region} focus · ` : ""}{s.images?.length || 0} photos</p>
                      {s.analysis ? (
                        <div className="flex gap-3 mt-1.5 text-xs">
                          <span>Density <b>{s.analysis.density_score}</b></span>
                          <span>Coverage <b>{s.analysis.coverage_score}</b></span>
                          <span>Overall <b>{s.analysis.overall_score}</b></span>
                        </div>
                      ) : <p className="text-xs text-muted-foreground mt-1.5">Not analyzed</p>}
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-foreground transition-colors" />
                  </div>
                </motion.button>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
