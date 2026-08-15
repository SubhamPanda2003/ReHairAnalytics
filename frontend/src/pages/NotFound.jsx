import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Activity, ArrowLeft } from "lucide-react";

export default function NotFound() {
  const { user } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 px-5 text-center" data-testid="not-found-page">
      <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center">
        <Activity className="w-6 h-6 text-primary-foreground" />
      </div>
      <h1 className="font-heading text-3xl font-bold tracking-tight">Page not found</h1>
      <p className="text-muted-foreground max-w-sm">The page you're looking for doesn't exist or may have moved.</p>
      <Button onClick={() => navigate(user ? "/dashboard" : "/")} className="rounded-full mt-2" data-testid="not-found-home-btn">
        <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to {user ? "Dashboard" : "Home"}
      </Button>
    </div>
  );
}
