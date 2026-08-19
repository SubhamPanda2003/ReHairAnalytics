import React from "react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Lock, MessageCircle, LogOut } from "lucide-react";

/** Full-screen block shown in place of the app once a user has run out of
 * scan credits -- ProtectedRoute swaps this in for every route, so the whole
 * app (not just the scan flow) freezes until an admin raises their limit. */
export default function ScanLimitBlocker({ message, whatsappNumber }) {
  const { logout } = useAuth();
  const digits = (whatsappNumber || "").replace(/\D/g, "");
  const waLink = digits ? `https://wa.me/${digits}` : null;

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-6" data-testid="scan-limit-blocker">
      <div className="max-w-sm w-full text-center">
        <div className="w-14 h-14 rounded-2xl bg-accent flex items-center justify-center mx-auto mb-4">
          <Lock className="w-7 h-7 text-accent-foreground" />
        </div>
        <h1 className="font-heading text-2xl font-bold">Out of scan credits</h1>
        <p className="text-muted-foreground mt-2">{message}</p>
        {waLink && (
          <a href={waLink} target="_blank" rel="noreferrer" className="block mt-6">
            <Button className="rounded-full w-full">
              <MessageCircle className="w-4 h-4 mr-2" /> WhatsApp us{whatsappNumber ? ` at ${whatsappNumber}` : ""}
            </Button>
          </a>
        )}
        <Button variant="outline" className="rounded-full mt-3 w-full" onClick={logout}>
          <LogOut className="w-4 h-4 mr-2" /> Sign out
        </Button>
      </div>
    </div>
  );
}
