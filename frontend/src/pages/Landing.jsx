import React, { useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Activity, Camera, LineChart, ShieldCheck, Sparkles, Ruler, Clock, ArrowRight, Check, Stethoscope, X } from "lucide-react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
const login = () => {
  const redirectUrl = window.location.origin + "/dashboard";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

const features = [
  { icon: Camera, title: "Standardized Capture", desc: "Ghost-silhouette overlay guides you to shoot the same angle, distance and lighting every week." },
  { icon: Ruler, title: "Objective Measurement", desc: "AI estimates density, coverage and hairline position on a consistent 0–100 scale." },
  { icon: LineChart, title: "Trends Over Time", desc: "Interactive charts turn each weekly scan into a clear, comparable milestone." },
  { icon: Sparkles, title: "Plain-Language Insights", desc: "A concise, non-diagnostic summary explains exactly what changed between photos." },
];

const steps = [
  { n: "01", t: "Create your profile", d: "Tell us your hair type and goals in under a minute." },
  { n: "02", t: "Capture your baseline", d: "Upload front, top, left, right & back scalp photos." },
  { n: "03", t: "Track weekly", d: "Re-shoot each week using the alignment guide." },
  { n: "04", t: "Watch the trend", d: "Compare against baseline and read your AI summary." },
  { n: "05", t: "Consult a dermatologist", d: "When you're ready, book a real consultation and bring your trend with you." },
];

export default function Landing() {
  const { user } = useAuth();
  const navigate = useNavigate();
  useEffect(() => { if (user) navigate("/dashboard"); }, [user, navigate]);

  // Landed here via the global 401 handler (lib/api.js) after a session went
  // stale mid-visit, rather than a normal logged-out page view -- say so,
  // instead of silently bouncing them with no explanation.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("session_expired") === "1") {
      toast.error("Your session expired. Please log in again.");
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="landing-page">
      {/* Nav */}
      <header className="sticky top-0 z-50 glass border-b border-border">
        <div className="max-w-7xl mx-auto px-5 md:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center">
              <Activity className="w-5 h-5 text-primary-foreground" />
            </div>
            <span className="font-heading font-bold text-lg tracking-tight">ReHairAnalytics</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={login} data-testid="nav-login-btn" className="rounded-full">Log in</Button>
            <Button onClick={login} data-testid="nav-signup-btn" className="rounded-full">Get started</Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden hair-grid-bg">
        <div className="max-w-7xl mx-auto px-5 md:px-8 pt-20 pb-24 md:pt-28 md:pb-32 grid lg:grid-cols-12 gap-10 items-center">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold mb-4">
              <ShieldCheck className="w-3.5 h-3.5" /> Objective tracking · Not a medical diagnosis
            </div>
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground mb-6">
              <span className="text-foreground">Track</span>
              <ArrowRight className="w-3 h-3" />
              <span className="text-foreground">Measure</span>
              <ArrowRight className="w-3 h-3" />
              <span className="text-foreground">Connect</span>
            </div>
            <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tighter leading-[1.05]">
              Track your hair.<br /><span className="text-primary">Measure</span> your progress.
            </h1>
            <p className="mt-6 text-base md:text-lg text-muted-foreground max-w-xl leading-relaxed">
              Turn your hair-loss journey into measurable progress with standardized photos and longitudinal tracking — then bring your trend to a real dermatologist when you're ready to act on it.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={login} data-testid="hero-cta-btn" className="rounded-full h-12 px-7 text-base">
                Start Tracking Free <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
              <Button size="lg" variant="outline" onClick={login} data-testid="hero-consult-btn" className="rounded-full h-12 px-7 text-base">
                <Stethoscope className="w-4 h-4 mr-1.5" /> Find a Dermatologist
              </Button>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">No credit card · Google sign-in</p>
          </motion.div>

          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7, delay: 0.1 }} className="lg:col-span-5">
            <div className="relative rounded-3xl overflow-hidden border border-border shadow-2xl">
              <img src="https://images.unsplash.com/photo-1560264641-1b5191cc63e2?crop=entropy&cs=srgb&fm=jpg&q=85&w=900" alt="hair" className="w-full h-[420px] object-cover" />
              <div className="absolute bottom-4 left-4 right-4 glass rounded-2xl p-4 border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Density</p>
                    <p className="font-heading text-3xl font-bold">74<span className="text-base text-muted-foreground">/100</span></p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">vs Baseline</p>
                    <p className="font-heading text-2xl font-bold text-primary">+4.3%</p>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Standardized Photography */}
      <section className="bg-secondary/50 border-y border-border">
        <div className="max-w-7xl mx-auto px-5 md:px-8 py-20">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold mb-4">
              <Camera className="w-3.5 h-3.5" /> Our core differentiator
            </div>
            <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">Same conditions. Meaningful comparisons.</h2>
            <p className="text-muted-foreground leading-relaxed">
              Hair photos can look dramatically different because of lighting, angle, distance and hairstyle. ReHairAnalytics guides you to capture standardized images so your measurements are more comparable over time.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 gap-6 max-w-3xl mx-auto">
            <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
              className="rounded-2xl border border-destructive/30 bg-card p-6">
              <div className="flex items-center gap-2 mb-4 text-destructive font-semibold text-sm">
                <X className="w-4 h-4" /> Inconsistent photos
              </div>
              <div className="grid grid-cols-3 gap-2 mb-4">
                {[-12, 8, -5].map((deg, i) => (
                  <div key={i} className="aspect-square rounded-lg bg-secondary flex items-center justify-center">
                    <Camera className="w-6 h-6 text-muted-foreground" style={{ transform: `rotate(${deg}deg) scale(${0.85 + i * 0.1})` }} />
                  </div>
                ))}
              </div>
              <ul className="text-xs text-muted-foreground space-y-1.5">
                <li>Different lighting each time</li>
                <li>Random angle & distance</li>
                <li>Hard to compare week to week</li>
              </ul>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0.08 }}
              className="rounded-2xl border border-primary/30 bg-card p-6">
              <div className="flex items-center gap-2 mb-4 text-primary font-semibold text-sm">
                <Check className="w-4 h-4" /> Standardized photos
              </div>
              <div className="grid grid-cols-3 gap-2 mb-4">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="aspect-square rounded-lg bg-secondary flex items-center justify-center relative">
                    <div className="absolute inset-1.5 rounded border border-dashed border-primary/50" />
                    <Camera className="w-5 h-5 text-primary" />
                  </div>
                ))}
              </div>
              <ul className="text-xs text-muted-foreground space-y-1.5">
                <li>Ghost-silhouette alignment guide</li>
                <li>Same distance & framing every scan</li>
                <li>Measurements you can actually trust</li>
              </ul>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-7xl mx-auto px-5 md:px-8 py-20">
        <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">Built for consistency</h2>
        <p className="text-muted-foreground max-w-2xl mb-12">Everything you need to measure change reliably — the enemy of accurate tracking is inconsistency, so we designed around it.</p>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f, i) => (
            <motion.div key={f.title} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }}
              className="rounded-2xl border border-border bg-card p-6 hover:-translate-y-1 transition-transform duration-200">
              <div className="w-11 h-11 rounded-xl bg-accent flex items-center justify-center mb-4">
                <f.icon className="w-5 h-5 text-accent-foreground" />
              </div>
              <h3 className="font-heading font-semibold text-lg mb-1.5">{f.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Track + Consult */}
      <section className="max-w-7xl mx-auto px-5 md:px-8 py-20">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold mb-4">
            <Stethoscope className="w-3.5 h-3.5" /> Beyond tracking
          </div>
          <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">A trend on its own doesn't treat hair loss.</h2>
          <p className="text-muted-foreground leading-relaxed">
            ReHairAnalytics doesn't stop at a chart. Once you have a real trend, bring it into a real conversation — book a dermatologist directly in the app and walk in with evidence, not just a feeling that something's changed.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 gap-6 max-w-3xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
            className="rounded-2xl border border-border bg-card p-6">
            <div className="flex items-center gap-2 mb-4 text-primary font-semibold text-sm">
              <LineChart className="w-4 h-4" /> 1. Track
            </div>
            <ul className="text-xs text-muted-foreground space-y-1.5">
              <li>Weekly standardized scans</li>
              <li>Objective density, coverage & hairline scores</li>
              <li>A trend you can actually trust</li>
            </ul>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0.08 }}
            className="rounded-2xl border border-primary/30 bg-card p-6">
            <div className="flex items-center gap-2 mb-4 text-primary font-semibold text-sm">
              <Stethoscope className="w-4 h-4" /> 2. Consult
            </div>
            <ul className="text-xs text-muted-foreground space-y-1.5">
              <li>Browse admin-verified dermatologists</li>
              <li>Book a consultation in a few taps</li>
              <li>Bring your tracked history to the conversation</li>
            </ul>
          </motion.div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-secondary/50 border-y border-border">
        <div className="max-w-7xl mx-auto px-5 md:px-8 py-20">
          <div className="flex items-center gap-2 mb-3"><Clock className="w-5 h-5 text-primary" /><span className="text-xs uppercase tracking-[0.2em] font-semibold text-muted-foreground">How it works</span></div>
          <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-12">Five steps, from first photo to expert opinion</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-6">
            {steps.map((s) => (
              <div key={s.n} className="rounded-2xl bg-card border border-border p-6">
                <span className="font-heading text-3xl font-bold text-primary/40">{s.n}</span>
                <h3 className="font-heading font-semibold text-lg mt-3 mb-1.5">{s.t}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="max-w-7xl mx-auto px-5 md:px-8 py-20">
        <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">Simple pricing</h2>
        <p className="text-muted-foreground mb-12">Start free. Placeholder plans below — no charges during the MVP.</p>
        <div className="grid md:grid-cols-3 gap-6">
          {[
            { name: "Starter", price: "₹0", tag: "Forever free", feats: ["Weekly tracking", "Baseline + 4 comparisons", "AI summaries"], primary: false },
            { name: "Pro", price: "₹299", tag: "Placeholder", feats: ["Unlimited scans", "All 5 views", "Full trend charts", "Data export"], primary: true },
            { name: "Clinic", price: "Custom", tag: "Coming soon", feats: ["Multi-patient", "Team dashboard", "Priority AI"], primary: false },
          ].map((p) => (
            <div key={p.name} className={`rounded-2xl p-7 border ${p.primary ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card"}`}>
              <p className={`text-xs uppercase tracking-[0.2em] font-semibold ${p.primary ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{p.tag}</p>
              <h3 className="font-heading text-2xl font-bold mt-2">{p.name}</h3>
              <p className="font-heading text-4xl font-bold mt-3">{p.price}<span className={`text-sm font-medium ${p.primary ? "text-primary-foreground/70" : "text-muted-foreground"}`}>/mo</span></p>
              <ul className="mt-6 space-y-2.5">
                {p.feats.map((f) => <li key={f} className="flex items-center gap-2 text-sm"><Check className="w-4 h-4" /> {f}</li>)}
              </ul>
              <Button onClick={login} variant={p.primary ? "secondary" : "outline"} className="w-full mt-7 rounded-full" data-testid={`pricing-${p.name.toLowerCase()}-btn`}>Get started</Button>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-5 md:px-8 py-10 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center"><Activity className="w-4 h-4 text-primary-foreground" /></div>
            <span className="font-heading font-semibold">ReHairAnalytics</span>
          </div>
          <p className="text-xs text-muted-foreground max-w-md text-center md:text-right">ReHairAnalytics provides objective photographic measurements only. It does not diagnose hair loss or provide medical advice.</p>
        </div>
      </footer>
    </div>
  );
}
