import React from "react";
import { motion } from "framer-motion";
import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { Button } from "@/components/ui/button";
import MetricDelta from "@/components/MetricDelta";
import { FlaskConical, Layers, ImageIcon, ArrowRight } from "lucide-react";

// Illustrative numbers only -- shaped like a real weekly report (see
// pages/Report.jsx) but fabricated for the marketing page, not tied to any
// account or API call. noiseFloor mirrors the same "within normal
// variation" treatment MetricDelta gives real scans.
const STATS = [
  { label: "Density", value: 78, baseline: 74, noiseFloor: 5 },
  { label: "Coverage", value: 81, baseline: 79, noiseFloor: 5 },
  { label: "Hairline", value: 74, baseline: 70, noiseFloor: 5 },
];
const OVERALL = { value: 79, baseline: 75, noiseFloor: 5 };

const REGIONS = [
  { name: "Front", tone: "from-emerald-400/50 to-sky-400/50" },
  { name: "Left", tone: "from-amber-400/50 to-rose-400/50" },
  { name: "Right", tone: "from-sky-400/50 to-indigo-400/50" },
  { name: "Crown", tone: "from-indigo-500/50 to-slate-500/50" },
  { name: "Hairline", tone: "from-emerald-400/50 to-amber-400/50" },
  { name: "Back", tone: "from-slate-500/50 to-indigo-500/50" },
];

const TREND = [
  { label: "Wk 1", overall: 70 },
  { label: "Wk 2", overall: 72 },
  { label: "Wk 3", overall: 74 },
  { label: "Wk 4", overall: 73 },
  { label: "Wk 5", overall: 76 },
  { label: "Wk 6", overall: 79 },
];

/** Marketing-page preview of what a weekly report looks like. Purely
 * presentational (fabricated numbers, no photos, no API calls) -- login is
 * owned by the caller so the real OAuth redirect logic stays in one place. */
export default function SampleReportPreview({ onGetStarted }) {
  return (
    <section className="max-w-7xl mx-auto px-5 md:px-8 py-20" data-testid="sample-report-section">
      <div className="text-center max-w-2xl mx-auto mb-12">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold mb-4">
          <FlaskConical className="w-3.5 h-3.5" /> What you get
        </div>
        <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">A real report, not just a photo album</h2>
        <p className="text-muted-foreground leading-relaxed">
          Every scan turns into an objective, plain-language report like this one. Numbers below are illustrative — yours is generated fresh from your own weekly photos.
        </p>
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
        className="rounded-3xl border border-border bg-card p-6 md:p-8 max-w-4xl mx-auto shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="font-heading font-bold text-lg">ReHairAnalytics</p>
            <p className="text-xs text-muted-foreground">Objective hair tracking report</p>
          </div>
          <span className="text-[10px] font-semibold uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-secondary text-muted-foreground shrink-0">Sample data</span>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {STATS.map((s) => (
            <div key={s.label} className="rounded-2xl border border-border p-4">
              <p className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-1.5">{s.label}</p>
              <p className="font-heading text-2xl font-bold">{s.value}</p>
              <MetricDelta current={s.value} baseline={s.baseline} noiseFloor={s.noiseFloor} />
            </div>
          ))}
          <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4">
            <p className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-1.5">Overall</p>
            <p className="font-heading text-2xl font-bold text-primary">{OVERALL.value}</p>
            <MetricDelta current={OVERALL.value} baseline={OVERALL.baseline} noiseFloor={OVERALL.noiseFloor} />
          </div>
        </div>

        {/* Measurement quality strip */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 text-xs text-muted-foreground border border-border rounded-2xl px-4 py-3 mb-6">
          <span className="font-semibold text-foreground">Measurement quality</span>
          <span>Confidence <b className="text-foreground">88%</b> (High)</span>
          <span>Photo quality <b className="text-foreground">84</b></span>
          <span>Visible scalp <b className="text-foreground">27%</b></span>
        </div>

        {/* Baseline vs latest -- placeholders, not real photos */}
        <div className="grid sm:grid-cols-2 gap-4 mb-6">
          {["Baseline", "Latest"].map((label) => (
            <div key={label}>
              <div className="aspect-[4/3] rounded-2xl bg-secondary flex items-center justify-center">
                <ImageIcon className="w-8 h-8 text-muted-foreground/60" />
              </div>
              <p className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mt-2 text-center">{label}</p>
            </div>
          ))}
        </div>

        {/* Visual change map */}
        <div className="mb-6">
          <p className="text-sm font-semibold mb-3 flex items-center gap-1.5"><Layers className="w-4 h-4 text-primary" /> Visual change map</p>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {REGIONS.map((r) => (
              <div key={r.name}>
                <div className={`aspect-square rounded-xl bg-gradient-to-br ${r.tone}`} />
                <p className="text-[10px] text-muted-foreground mt-1 text-center">{r.name}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Trend chart */}
        <div className="mb-6">
          <p className="text-sm font-semibold mb-3">Trend over time</p>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={TREND} margin={{ left: -20, right: 8 }}>
              <defs>
                <linearGradient id="sample-gd" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }} />
              <Area type="monotone" dataKey="overall" stroke="hsl(var(--chart-1))" strokeWidth={2.5} fill="url(#sample-gd)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Latest insight */}
        <div className="rounded-2xl bg-secondary/50 p-4">
          <p className="text-sm font-semibold mb-1.5">Latest insight</p>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Overall coverage and density are both trending up over the last six weeks, with the clearest gains around the crown. Hairline position is holding steady. Keep scanning weekly to confirm this trend clears normal measurement noise.
          </p>
        </div>

        <p className="text-[11px] text-muted-foreground mt-6 text-center">
          Illustrative example, not real user data. Reports present objective photographic measurements only — never a diagnosis.
        </p>
      </motion.div>

      <div className="text-center mt-8">
        <Button size="lg" onClick={onGetStarted} data-testid="sample-report-cta-btn" className="rounded-full h-12 px-7 text-base">
          Start Tracking Free <ArrowRight className="w-4 h-4 ml-1" />
        </Button>
      </div>
    </section>
  );
}
