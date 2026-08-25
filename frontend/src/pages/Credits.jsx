import React, { useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import BuyCreditsButton from "@/components/BuyCreditsButton";
import { CreditCard, Camera, Sparkles as SparklesIcon, Lock } from "lucide-react";

export default function Credits() {
  const { user, quota } = useAuth();
  const unlimited = user?.role !== "user" || quota?.limit == null;
  const exhausted = !unlimited && quota.remaining <= 0;

  useEffect(() => {
    // React Router doesn't trigger a real page load, so the base Meta Pixel
    // snippet in public/index.html only ever fires PageView once -- this is
    // a separate, explicit fire for this specific page since it's the one
    // most relevant to ad conversion tracking (viewing pricing/credits).
    if (typeof window.fbq === "function") {
      window.fbq("track", "ViewContent", { content_name: "Credits" });
    }
  }, []);

  return (
    <div className="min-h-screen bg-background" data-testid="credits-page">
      <Navbar />
      <main className="max-w-3xl mx-auto px-5 md:px-8 py-8">
        <h1 className="font-heading text-3xl font-bold tracking-tight mb-2">Credits</h1>
        <p className="text-muted-foreground mb-8">Every scan uses credits — top up anytime, they never expire.</p>

        {exhausted && (
          <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-6 mb-6 flex items-start gap-3" data-testid="credits-exhausted-banner">
            <div className="w-9 h-9 rounded-xl bg-destructive/10 flex items-center justify-center shrink-0">
              <Lock className="w-4 h-4 text-destructive" />
            </div>
            <div>
              <p className="font-medium">Out of scan credits</p>
              <p className="text-sm text-muted-foreground mt-0.5">{quota.exhausted_message}</p>
            </div>
          </div>
        )}

        <div className="rounded-2xl border border-border bg-card p-6 mb-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-xl bg-accent flex items-center justify-center shrink-0">
              <CreditCard className="w-4 h-4 text-accent-foreground" />
            </div>
            <p className="font-medium">Your balance</p>
          </div>
          {unlimited ? (
            <p className="text-3xl font-heading font-bold mt-3">Unlimited</p>
          ) : (
            <>
              <p className="text-3xl font-heading font-bold mt-3" data-testid="credits-remaining">
                {quota.remaining} <span className="text-lg text-muted-foreground font-normal">/ {quota.limit} credits</span>
              </p>
              <div className="flex items-center gap-4 mt-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5"><Camera className="w-3.5 h-3.5" /> Normal scan: {quota.scan_cost} credit</span>
                <span className="flex items-center gap-1.5"><SparklesIcon className="w-3.5 h-3.5" /> Precision scan: {quota.precision_scan_cost} credits</span>
              </div>
            </>
          )}
        </div>

        {!unlimited && (
          <div className="rounded-2xl border border-border bg-card p-6">
            <p className="font-medium mb-1">Starter Pack</p>
            <p className="text-sm text-muted-foreground mb-4">20 credits — enough for 10 normal scans, or a mix with precision scans.</p>
            <div className="flex items-center justify-between">
              <span className="text-2xl font-heading font-bold">₹100</span>
              <BuyCreditsButton className="rounded-full" label="Buy now" />
            </div>
          </div>
        )}

        {quota?.whatsapp_number && !unlimited && (
          <p className="text-xs text-muted-foreground text-center mt-6">
            Need a custom plan? WhatsApp us at {quota.whatsapp_number}.
          </p>
        )}
      </main>
    </div>
  );
}
