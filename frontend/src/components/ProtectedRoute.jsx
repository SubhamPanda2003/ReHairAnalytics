import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";
import ScanLimitBlocker from "@/components/ScanLimitBlocker";

export default function ProtectedRoute({ children, requireCredits = false }) {
  const { user, loading, quota } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) return <Navigate to="/" replace state={{ from: location }} />;

  // Only plain "user" accounts carry a scan quota (see backend
  // services/quota.py). Exhausting it only blocks routes that opt in via
  // requireCredits (Dashboard, New Scan) -- Timeline, Consult, Settings and
  // Credits itself stay reachable so a user can still see their history or
  // buy more credits without being locked out of the whole app.
  if (requireCredits && user.role === "user" && quota?.limit != null && quota.remaining <= 0) {
    return <ScanLimitBlocker message={quota.exhausted_message} whatsappNumber={quota.whatsapp_number} />;
  }
  return children;
}
