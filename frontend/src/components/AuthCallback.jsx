import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash;
    const sessionId = hash.split("session_id=")[1]?.split("&")[0];

    const run = async () => {
      try {
        const res = await api.post("/auth/session", { session_id: sessionId });
        setUser(res.data.user);
        window.history.replaceState(null, "", "/dashboard");
        const me = await api.get("/auth/me");
        setUser(me.data);
        if (!me.data.profile) navigate("/onboarding", { replace: true });
        else navigate("/dashboard", { replace: true, state: { user: me.data } });
      } catch (e) {
        navigate("/", { replace: true });
      }
    };
    run();
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4" data-testid="auth-callback">
      <Loader2 className="w-8 h-8 animate-spin text-primary" />
      <p className="text-muted-foreground text-sm">Signing you in…</p>
    </div>
  );
}
