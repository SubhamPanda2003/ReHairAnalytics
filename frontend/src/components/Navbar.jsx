import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Activity, LayoutDashboard, Upload, LineChart, Settings, LogOut, Stethoscope, ShieldCheck, Users, CreditCard } from "lucide-react";

const baseLinks = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, id: "nav-dashboard" },
  { to: "/upload", label: "New Scan", icon: Upload, id: "nav-upload" },
  { to: "/timeline", label: "Timeline", icon: LineChart, id: "nav-timeline" },
  { to: "/dermatologists", label: "Consult", icon: Stethoscope, id: "nav-consult" },
];

export default function Navbar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const role = user?.role || "user";
  const links = [...baseLinks];
  // Only plain "user" accounts carry a scan quota (services/quota.py) --
  // admins/coaches/dermatologists are never limited, so a credits tab is
  // meaningless for them.
  if (role === "user") links.push({ to: "/credits", label: "Credits", icon: CreditCard, id: "nav-credits" });
  if (role === "dermatologist" || user?.is_dermatologist) links.push({ to: "/derm", label: "Practice", icon: Stethoscope, id: "nav-practice" });
  if (role === "coach") links.push({ to: "/coach", label: "Patients", icon: Users, id: "nav-coach" });
  if (role === "admin" || role === "super_admin") links.push({ to: "/admin", label: "Admin", icon: ShieldCheck, id: "nav-admin" });
  links.push({ to: "/settings", label: "Settings", icon: Settings, id: "nav-settings" });

  return (
    <header className="sticky top-0 z-50 glass border-b border-border" data-testid="app-navbar">
      <div className="max-w-7xl mx-auto px-5 md:px-8 h-16 flex items-center justify-between">
        <Link to="/dashboard" className="flex items-center gap-2.5" data-testid="nav-logo">
          <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center">
            <Activity className="w-5 h-5 text-primary-foreground" />
          </div>
          <span className="font-heading font-bold text-lg tracking-tight">ReHairAnalytics</span>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {links.map((l) => {
            const active = location.pathname === l.to;
            return (
              <button
                key={l.to}
                data-testid={l.id}
                onClick={() => navigate(l.to)}
                className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors duration-200 ${
                  active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary"
                }`}
              >
                <l.icon className="w-4 h-4" />
                {l.label}
              </button>
            );
          })}
        </nav>

        <div className="flex items-center gap-3">
          {user?.picture ? (
            <img src={user.picture} alt="me" className="w-8 h-8 rounded-full object-cover" referrerPolicy="no-referrer" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-accent-foreground text-xs font-semibold">
              {user?.name?.[0] || "U"}
            </div>
          )}
          <Button variant="ghost" size="icon" onClick={logout} data-testid="nav-logout" title="Log out">
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <nav className="md:hidden flex items-center border-t border-border">
        {links.map((l) => {
          const active = location.pathname === l.to;
          return (
            <button key={l.to} onClick={() => navigate(l.to)} data-testid={`${l.id}-mobile`}
              className={`flex-1 min-w-0 flex flex-col items-center gap-0.5 px-1 py-1.5 rounded-lg text-[10px] ${active ? "text-primary" : "text-muted-foreground"}`}>
              <l.icon className="w-5 h-5 shrink-0" />
              <span className="w-full truncate text-center">{l.label}</span>
            </button>
          );
        })}
      </nav>
    </header>
  );
}
