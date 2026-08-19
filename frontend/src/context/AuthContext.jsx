import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [quota, setQuota] = useState(null); // { limit, used, remaining, exhausted_message, whatsapp_number } | null

  const refreshQuota = useCallback(async () => {
    try {
      const res = await api.get("/scan/quota");
      setQuota(res.data);
    } catch (e) {
      setQuota(null);
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const res = await api.get("/auth/me");
      setUser(res.data);
      await refreshQuota();
    } catch (e) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [refreshQuota]);

  useEffect(() => {
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) {}
    setUser(null);
    setQuota(null);
    window.location.href = "/";
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, checkAuth, logout, quota, refreshQuota }}>
      {children}
    </AuthContext.Provider>
  );
};
