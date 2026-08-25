import React from "react";
import { Button } from "@/components/ui/button";
import BuyCreditsButton from "@/components/BuyCreditsButton";
import Navbar from "@/components/Navbar";
import { Lock, MessageCircle } from "lucide-react";

/** Blocks a single route (Dashboard, New Scan) once a user has run out of
 * scan credits -- ProtectedRoute swaps this in for just those routes via its
 * requireCredits prop, so Timeline/Consult/Settings/Credits stay reachable
 * through the Navbar rendered here rather than the whole app freezing. */
export default function ScanLimitBlocker({ message, whatsappNumber }) {
  const digits = (whatsappNumber || "").replace(/\D/g, "");
  const waLink = digits ? `https://wa.me/${digits}` : null;

  return (
    <div className="min-h-screen bg-background" data-testid="scan-limit-blocker">
      <Navbar />
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-6">
        <div className="max-w-sm w-full text-center">
          <div className="w-14 h-14 rounded-2xl bg-accent flex items-center justify-center mx-auto mb-4">
            <Lock className="w-7 h-7 text-accent-foreground" />
          </div>
          <h1 className="font-heading text-2xl font-bold">Out of scan credits</h1>
          <p className="text-muted-foreground mt-2">{message}</p>
          <BuyCreditsButton className="rounded-full w-full mt-6" />
          {waLink && (
            <a href={waLink} target="_blank" rel="noreferrer" className="block mt-3">
              <Button variant="outline" className="rounded-full w-full">
                <MessageCircle className="w-4 h-4 mr-2" /> WhatsApp us{whatsappNumber ? ` at ${whatsappNumber}` : ""}
              </Button>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
