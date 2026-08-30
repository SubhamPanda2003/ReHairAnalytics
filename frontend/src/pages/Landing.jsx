import React, { useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Activity, Camera, LineChart, ShieldCheck, Sparkles, Ruler, Clock, ArrowRight, Check, Stethoscope, X, Download, Lock, Trash2, BadgeCheck } from "lucide-react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
const login = () => {
  const redirectUrl = window.location.origin + "/dashboard";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

const features = [
  { icon: Ruler, title: "A Number, Not a Feeling", desc: "AI estimates density, coverage and hairline position on a consistent 0–100 scale — so \"I think it's thinner\" becomes something you can actually act on." },
  { icon: LineChart, title: "Catch It Before the Mirror Does", desc: "Weekly scans surface small changes months before they're obvious in person, so you find out early enough to still do something." },
  { icon: Sparkles, title: "What Changed, And Where", desc: "A concise, non-diagnostic summary explains exactly what moved — crown, hairline, temples — not just one vague score." },
  { icon: BadgeCheck, title: "A Real Second Opinion", desc: "Opt in anytime to have a real hair coach personally check your report before you decide anything — a second set of eyes, not just an algorithm." },
];

const privacyPoints = [
  { icon: Lock, title: "Only you can see it", desc: "Every photo request is checked against your account — no public links, no other user can browse your gallery." },
  { icon: ShieldCheck, title: "Never sold or shared", desc: "Photos are used only to generate your own measurements. They're visible to a dermatologist only if you personally choose to share your history with them." },
  { icon: Trash2, title: "Delete anytime", desc: "Remove any photo permanently from Settings whenever you want — no waiting, no support ticket." },
];

const steps = [
  { n: "01", t: "Tell us where you're starting", d: "Hair type, goals, and what you're already doing about it — under a minute." },
  { n: "02", t: "Get your baseline reading", d: "Front, top, left, right & back — one full scalp reading to measure everything against." },
  { n: "03", t: "Re-scan weekly, no guessing", d: "The alignment guide keeps every photo comparable, so it's hair vs. hair, not lighting vs. lighting." },
  { n: "04", t: "Get your verdict", d: "See if you're improving, holding steady, or still declining — region by region, not one fuzzy score." },
  { n: "05", t: "Bring the evidence to a dermatologist", d: "Skip \"I think it's worse\" — show up with real data and get a decision made faster." },
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
            <Button variant="ghost" onClick={login} data-testid="nav-login-btn" className="rounded-full hidden sm:inline-flex">Log in</Button>
            <Button onClick={login} data-testid="nav-signup-btn" className="rounded-full">Get started</Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden hair-grid-bg">
        <div className="max-w-7xl mx-auto px-5 md:px-8 pt-20 pb-24 md:pt-28 md:pb-32 grid lg:grid-cols-12 gap-10 items-center">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold mb-4">
              <Stethoscope className="w-3.5 h-3.5" /> For people already treating hair loss
            </div>
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground mb-6">
              <span className="text-foreground">Track</span>
              <ArrowRight className="w-3 h-3" />
              <span className="text-foreground">Measure</span>
              <ArrowRight className="w-3 h-3" />
              <span className="text-foreground">Decide</span>
            </div>
            <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tighter leading-[1.05]">
              Is your treatment<br /><span className="text-primary">actually working?</span>
            </h1>
            <p className="mt-6 text-base md:text-lg text-muted-foreground max-w-xl leading-relaxed">
              Minoxidil, finasteride, PRP — you can't tell from the mirror, and finding out six months too late is expensive. Get an objective reading every week, and real evidence to bring to a dermatologist.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={login} data-testid="hero-cta-btn" className="rounded-full h-12 px-7 text-base">
                Get My First Reading <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
              <Button size="lg" variant="outline" onClick={login} data-testid="hero-consult-btn" className="rounded-full h-12 px-7 text-base">
                <Stethoscope className="w-4 h-4 mr-1.5" /> Talk to a Dermatologist
              </Button>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">500+ scans tracked so far · Not a medical diagnosis · No credit card</p>
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

      {/* Sample report */}
      <section className="max-w-7xl mx-auto px-5 md:px-8 py-10 text-center">
        <p className="text-muted-foreground mb-3">See what a real verdict looks like on paper.</p>
        <a href="/sample-report.pdf" download="ReHairAnalytics-Sample-Report.pdf" data-testid="sample-report-download">
          <Button size="lg" variant="outline" className="rounded-full h-12 px-7 text-base">
            <Download className="w-4 h-4 mr-1.5" /> Download sample reading
          </Button>
        </a>
      </section>

      {/* Privacy */}
      <section className="max-w-7xl mx-auto px-5 md:px-8 py-16">
        <div className="text-center max-w-2xl mx-auto mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold mb-4">
            <ShieldCheck className="w-3.5 h-3.5" /> Your photos, protected
          </div>
          <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">Private by default</h2>
          <p className="text-muted-foreground leading-relaxed">A scalp photo is personal. Here's exactly how yours is handled.</p>
        </div>
        <div className="grid sm:grid-cols-3 gap-6 max-w-4xl mx-auto">
          {privacyPoints.map((p, i) => (
            <motion.div key={p.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }}
              className="rounded-2xl border border-border bg-card p-6">
              <div className="w-11 h-11 rounded-xl bg-accent flex items-center justify-center mb-4">
                <p.icon className="w-5 h-5 text-accent-foreground" />
              </div>
              <h3 className="font-heading font-semibold text-lg mb-1.5">{p.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{p.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Standardized Photography */}
      <section className="bg-secondary/50 border-y border-border">
        <div className="max-w-7xl mx-auto px-5 md:px-8 py-20">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold mb-4">
              <Camera className="w-3.5 h-3.5" /> Why the verdict holds up
            </div>
            <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">Same conditions. A verdict you can trust.</h2>
            <p className="text-muted-foreground leading-relaxed">
              Hair photos can look dramatically different because of lighting, angle, distance and hairstyle — which is how people end up arguing with themselves in the mirror for months. ReHairAnalytics guides you to capture standardized images so the answer holds up, not just a feeling.
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
        <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-3">Built to answer one question</h2>
        <p className="text-muted-foreground max-w-2xl mb-12">"Is it working?" Everything below exists to answer that reliably — the enemy of a trustworthy answer is inconsistency, so we designed around it.</p>
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

      {/* How it works */}
      <section className="bg-secondary/50 border-y border-border">
        <div className="max-w-7xl mx-auto px-5 md:px-8 py-20">
          <div className="flex items-center gap-2 mb-3"><Clock className="w-5 h-5 text-primary" /><span className="text-xs uppercase tracking-[0.2em] font-semibold text-muted-foreground">How it works</span></div>
          <h2 className="font-heading text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight mb-12">Five steps to a straight answer</h2>
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
