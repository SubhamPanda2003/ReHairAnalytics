import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";
import ScanLimitBlocker from "@/components/ScanLimitBlocker";

export default function ProtectedRoute({ children }) {
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
  // services/quota.py) -- exhausting it freezes every route behind this
  // guard, not just the scan/upload flow, until an admin raises the limit.
  if (user.role === "user" && quota?.limit != null && quota.remaining <= 0) {
    return <ScanLimitBlocker message={quota.exhausted_message} whatsappNumber={quota.whatsapp_number} />;
  }
  return children;
}
