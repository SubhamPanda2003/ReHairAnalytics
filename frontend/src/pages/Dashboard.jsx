import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { LineChart, Line, AreaChart, Area, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { Flame, ImageIcon, TrendingUp, TrendingDown, Minus, Plus, Camera, ArrowRight, Sparkles, Bell } from "lucide-react";

const fetchProgress = async () => (await api.get("/progress")).data;
const fetchTimeline = async () => (await api.get("/timeline")).data;

const Trend = ({ value }) => {
  if (value === null || value === undefined) return <span className="text-muted-foreground text-sm flex items-center gap-1"><Minus className="w-3.5 h-3.5" /> —</span>;
  if (value > 0) return <span className="text-primary text-sm font-semibold flex items-center gap-1"><TrendingUp className="w-3.5 h-3.5" /> +{value}</span>;
  if (value < 0) return <span className="text-destructive text-sm font-semibold flex items-center gap-1"><TrendingDown className="w-3.5 h-3.5" /> {value}</span>;
  return <span className="text-muted-foreground text-sm flex items-center gap-1"><Minus className="w-3.5 h-3.5" /> No change</span>;
};

const Card = ({ children, className = "", delay = 0, ...rest }) => (
  <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
    className={`rounded-2xl border border-border bg-card p-6 ${className}`} {...rest}>{children}</motion.div>
);

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data: progress, isLoading } = useQuery({ queryKey: ["progress"], queryFn: fetchProgress });
  const { data: timeline } = useQuery({ queryKey: ["timeline"], queryFn: fetchTimeline });

  const points = progress?.points || [];
  const latest = progress?.latest;
  const est = progress?.estimated_progress;
  const latestSession = timeline?.[timeline.length - 1];
  const latestImg = latestSession?.images?.[0];

  const reminderOn = !!user?.profile?.reminder_enabled;
  const daysSince = progress?.days_since_last;
  const due = reminderOn && (daysSince === null || daysSince === undefined ? false : daysSince >= 7);

  useEffect(() => {
    if (due && "Notification" in window && Notification.permission === "granted") {
      try { new Notification("ReHairAnalytics", { body: "Time for your weekly hair scan 📸" }); } catch (e) {}
    }
  }, [due]);

  return (
    <div className="min-h-screen bg-background" data-testid="dashboard-page">
      <Navbar />
      <main className="max-w-7xl mx-auto px-5 md:px-8 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight">Your progress</h1>
            <p className="text-muted-foreground mt-1">Objective measurements from your weekly scans.</p>
          </div>
          <Button onClick={() => navigate("/upload")} className="rounded-full h-11 px-6" data-testid="dashboard-upload-btn">
            <Camera className="w-4 h-4 mr-1.5" /> New scan
          </Button>
        </div>

        {due && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
            className="flex items-center justify-between gap-4 rounded-2xl border border-primary/30 bg-primary/10 px-5 py-4 mb-6" data-testid="reminder-banner">
            <div className="flex items-center gap-3">
              <Bell className="w-5 h-5 text-primary" />
              <p className="text-sm font-medium">It's been {daysSince} days since your last scan — time for this week's capture.</p>
            </div>
            <Button size="sm" onClick={() => navigate("/upload")} className="rounded-full" data-testid="reminder-scan-btn">Scan now</Button>
          </motion.div>
        )}

        {isLoading ? (
          <div className="text-muted-foreground py-20 text-center">Loading…</div>
        ) : points.length === 0 ? (
          <Card className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-accent flex items-center justify-center mx-auto mb-4">
              <Camera className="w-7 h-7 text-accent-foreground" />
            </div>
            <h2 className="font-heading text-xl font-semibold">Capture your baseline</h2>
            <p className="text-muted-foreground mt-2 max-w-md mx-auto">Upload your first set of scalp photos to establish a baseline. Every future scan compares against it.</p>
            <Button onClick={() => navigate("/upload")} className="rounded-full mt-6" data-testid="empty-upload-btn">
              Start tracking <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </Card>
        ) : (
          <>
            {/* Metric cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6">
              <Card delay={0} data-testid="card-streak">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.15em] mb-3"><Flame className="w-4 h-4" /> Streak</div>
                <p className="font-heading text-4xl font-bold">{progress.streak}</p>
                <p className="text-sm text-muted-foreground mt-1">weekly scans</p>
              </Card>
              <Card delay={0.05} data-testid="card-latest-upload">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.15em] mb-3"><ImageIcon className="w-4 h-4" /> Latest</div>
                {latestImg ? (
                  <img src={fileUrl(latestImg.thumb_path)} alt="latest" className="w-full h-20 object-cover rounded-xl" />
                ) : <p className="font-heading text-2xl font-bold">—</p>}
                <p className="text-sm text-muted-foreground mt-2">{latest?.date ? new Date(latest.date).toLocaleDateString() : "—"}</p>
              </Card>
              <Card delay={0.1} data-testid="card-est-progress">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.15em] mb-3"><Sparkles className="w-4 h-4" /> Est. progress</div>
                <p className="font-heading text-4xl font-bold">{latest?.overall ?? "—"}</p>
                <div className="mt-1"><Trend value={est?.overall} /></div>
              </Card>
              <Card delay={0.15} data-testid="card-confidence">
                <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.15em] mb-3"><Plus className="w-4 h-4" /> Quality</div>
                <p className="font-heading text-4xl font-bold">{latest?.quality ?? "—"}</p>
                <p className="text-sm text-muted-foreground mt-1">avg image quality</p>
              </Card>
            </div>

            {/* Trend charts */}
            <div className="grid lg:grid-cols-3 gap-6 mb-6">
              <Card className="lg:col-span-2" delay={0.2} data-testid="chart-density">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-heading font-semibold text-lg">Density & coverage trend</h3>
                  <div className="flex items-center gap-4 text-xs">
                    <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-chart-1" /> Density</span>
                    <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-chart-2" /> Coverage</span>
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <AreaChart data={points} margin={{ left: -20, right: 8 }}>
                    <defs>
                      <linearGradient id="gd" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.35} /><stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0} /></linearGradient>
                      <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="hsl(var(--chart-2))" stopOpacity={0.35} /><stop offset="100%" stopColor="hsl(var(--chart-2))" stopOpacity={0} /></linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }} />
                    <Area type="monotone" dataKey="density" stroke="hsl(var(--chart-1))" strokeWidth={2.5} fill="url(#gd)" />
                    <Area type="monotone" dataKey="coverage" stroke="hsl(var(--chart-2))" strokeWidth={2.5} fill="url(#gc)" />
                  </AreaChart>
                </ResponsiveContainer>
              </Card>

              <Card delay={0.25} data-testid="chart-hairline">
                <h3 className="font-heading font-semibold text-lg mb-4">Hairline trend</h3>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={points} margin={{ left: -20, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }} />
                    <Line type="monotone" dataKey="hairline" stroke="hsl(var(--chart-3))" strokeWidth={2.5} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
            </div>

            {/* Timeline preview */}
            <Card delay={0.3} data-testid="dashboard-timeline">
              <div className="flex items-center justify-between mb-5">
                <h3 className="font-heading font-semibold text-lg">Recent milestones</h3>
                <Button variant="ghost" size="sm" onClick={() => navigate("/timeline")} className="rounded-full" data-testid="view-timeline-btn">View all <ArrowRight className="w-4 h-4 ml-1" /></Button>
              </div>
              <div className="flex gap-4 overflow-x-auto pb-2">
                {[...timeline].reverse().map((s) => (
                  <button key={s.id} onClick={() => navigate(`/results/${s.id}`)} data-testid={`milestone-${s.week_number}`}
                    className="min-w-[160px] rounded-2xl border border-border overflow-hidden text-left hover:-translate-y-1 transition-transform duration-200 bg-secondary/40">
                    {s.images?.[0] ? <img src={fileUrl(s.images[0].thumb_path)} alt="" className="w-full h-24 object-cover" /> : <div className="w-full h-24 bg-muted" />}
                    <div className="p-3">
                      <p className="font-heading font-semibold">{new Date(s.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</p>
                      <p className="text-xs text-muted-foreground">{s.analysis ? `Overall ${s.analysis.overall_score}` : "Not analyzed"}</p>
                    </div>
                  </button>
                ))}
              </div>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
