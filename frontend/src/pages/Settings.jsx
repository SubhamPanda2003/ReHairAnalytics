import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Moon, Download, ImageDown, Trash2, ShieldCheck, Ruler, Loader2, Bell, UserRound, Sparkles } from "lucide-react";
import BuyCreditsButton from "@/components/BuyCreditsButton";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export default function Settings() {
  const navigate = useNavigate();
  const { user, logout, quota } = useAuth();
  const qc = useQueryClient();
  const { data: coachInfo } = useQuery({ queryKey: ["my-coach"], queryFn: async () => (await api.get("/coach/mine")).data });
  const [dark, setDark] = useState(document.documentElement.classList.contains("dark"));
  const [units, setUnits] = useState(localStorage.getItem("units") || "metric");
  const [busy, setBusy] = useState(false);
  const [reminderOn, setReminderOn] = useState(!!user?.profile?.reminder_enabled);
  const [reminderDay, setReminderDay] = useState(user?.profile?.reminder_day || "Monday");

  const saveReminder = async (enabled, day) => {
    setReminderOn(enabled); setReminderDay(day);
    try {
      if (enabled && "Notification" in window && Notification.permission === "default") {
        await Notification.requestPermission();
      }
      await api.post("/profile", { reminder_enabled: enabled, reminder_day: day });
      toast.success(enabled ? `Weekly reminder set for ${day}` : "Reminder turned off");
    } catch (e) { toast.error("Could not save reminder"); }
  };

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  const exportData = async () => {
    try {
      const res = await api.get("/export");
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "rehairanalytics-export.json"; a.click();
      URL.revokeObjectURL(url);
      toast.success("Data exported");
    } catch (e) { toast.error("Export failed"); }
  };

  const downloadImages = async () => {
    setBusy(true);
    try {
      const res = await api.get("/export");
      const imgs = res.data.images || [];
      if (!imgs.length) { toast.info("No images to download"); setBusy(false); return; }
      for (const img of imgs) {
        const r = await api.get(`/files/${img.storage_path}`, { responseType: "blob" });
        const url = URL.createObjectURL(r.data);
        const a = document.createElement("a");
        a.href = url; a.download = `${img.view}_${img.id.slice(0, 6)}.jpg`; a.click();
        URL.revokeObjectURL(url);
      }
      toast.success(`Downloaded ${imgs.length} images`);
    } catch (e) { toast.error("Download failed"); }
    setBusy(false);
  };

  const toggleCoachShare = async (share) => {
    try {
      await api.post("/coach/share", { share });
      qc.invalidateQueries({ queryKey: ["my-coach"] });
      toast.success(share ? "Now sharing reports with your coach" : "Sharing turned off");
    } catch (e) { toast.error("Could not update sharing"); }
  };

  const deleteAccount = async () => {
    try {
      await api.delete("/account");
      toast.success("Account deleted");
      logout();
    } catch (e) { toast.error("Delete failed"); }
  };

  const Row = ({ icon: Icon, title, desc, children, testId }) => (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 py-5 border-b border-border last:border-0" data-testid={testId}>
      <div className="flex items-start gap-3 min-w-0">
        <div className="w-9 h-9 rounded-xl bg-accent flex items-center justify-center shrink-0"><Icon className="w-4 h-4 text-accent-foreground" /></div>
        <div className="min-w-0"><p className="font-medium">{title}</p><p className="text-sm text-muted-foreground">{desc}</p></div>
      </div>
      <div className="shrink-0 pl-12 sm:pl-0">{children}</div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background" data-testid="settings-page">
      <Navbar />
      <main className="max-w-3xl mx-auto px-5 md:px-8 py-8">
        <h1 className="font-heading text-3xl font-bold tracking-tight mb-2">Settings</h1>
        <p className="text-muted-foreground mb-8">{user?.name} · {user?.email}</p>

        {user?.role === "user" && quota?.limit != null && (
          <div className="rounded-2xl border border-border bg-card px-6 mb-6">
            <Row
              icon={Sparkles}
              title="Scan credits"
              desc={`${quota.remaining} of ${quota.limit} remaining. A normal scan costs ${quota.scan_cost}, a precision scan costs ${quota.precision_scan_cost}.`}
              testId="setting-credits"
            >
              <BuyCreditsButton className="rounded-full" label="Buy 100 — ₹499" />
            </Row>
          </div>
        )}

        <div className="rounded-2xl border border-border bg-card px-6 mb-6">
          <Row icon={Moon} title="Dark mode" desc="Switch to the clinical night view." testId="setting-dark">
            <Switch checked={dark} onCheckedChange={setDark} data-testid="dark-mode-switch" />
          </Row>
          <Row icon={Ruler} title="Units" desc="Display preference for measurements." testId="setting-units">
            <Select value={units} onValueChange={(v) => { setUnits(v); localStorage.setItem("units", v); }}>
              <SelectTrigger className="w-32 rounded-xl" data-testid="units-select"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="metric">Metric</SelectItem><SelectItem value="imperial">Imperial</SelectItem></SelectContent>
            </Select>
          </Row>
        </div>

        <div className="rounded-2xl border border-border bg-card px-6 mb-6">
          <Row icon={Bell} title="Weekly reminder" desc="Get a nudge to capture your weekly scan." testId="setting-reminder">
            <Switch checked={reminderOn} onCheckedChange={(v) => saveReminder(v, reminderDay)} data-testid="reminder-switch" />
          </Row>
          {reminderOn && (
            <Row icon={Bell} title="Reminder day" desc="We'll remind you in-app (and via browser notification if allowed)." testId="setting-reminder-day">
              <Select value={reminderDay} onValueChange={(v) => saveReminder(true, v)}>
                <SelectTrigger className="w-40 rounded-xl" data-testid="reminder-day-select"><SelectValue /></SelectTrigger>
                <SelectContent>{DAYS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
              </Select>
            </Row>
          )}
        </div>

        <div className="rounded-2xl border border-border bg-card px-6 mb-6">
          <Row icon={Download} title="Export data" desc="Download all your sessions & analysis as JSON." testId="setting-export">
            <Button variant="outline" className="rounded-full" onClick={exportData} data-testid="export-btn">Export</Button>
          </Row>
          <Row icon={ImageDown} title="Download images" desc="Save every uploaded photo to your device." testId="setting-images">
            <Button variant="outline" className="rounded-full" onClick={downloadImages} disabled={busy} data-testid="download-images-btn">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Download"}
            </Button>
          </Row>
        </div>

        <div className="rounded-2xl border border-border bg-card px-6 mb-6">
          <Row icon={ShieldCheck} title="Privacy" desc="Your photos are private and used only for your measurements." testId="setting-privacy">
            <span className="text-xs text-muted-foreground">Private</span>
          </Row>
          <Row
            icon={UserRound}
            title="Hair coach"
            desc={coachInfo?.coach ? `Assigned: ${coachInfo.coach.name || "your coach"}. Sharing is opt-in and off unless you turn it on.` : "No coach assigned yet — check back once your admin pairs you with one."}
            testId="setting-coach"
          >
            {coachInfo?.coach ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Share reports</span>
                <Switch checked={!!coachInfo.share_with_coach} onCheckedChange={toggleCoachShare} data-testid="coach-share-switch" />
              </div>
            ) : (
              <span className="text-xs text-muted-foreground">Not assigned</span>
            )}
          </Row>
        </div>

        <div className="rounded-2xl border border-destructive/30 bg-card px-6">
          <Row icon={Trash2} title="Delete account" desc="Permanently remove your account, photos and data." testId="setting-delete">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" className="rounded-full" data-testid="delete-account-btn">Delete</Button>
              </AlertDialogTrigger>
              <AlertDialogContent className="rounded-3xl">
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete your account?</AlertDialogTitle>
                  <AlertDialogDescription>This permanently deletes your profile, all scans, images and analysis. This cannot be undone.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel className="rounded-full" data-testid="delete-cancel">Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={deleteAccount} className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90" data-testid="delete-confirm">Delete permanently</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </Row>
        </div>

        <p className="text-xs text-muted-foreground text-center mt-8">ReHairAnalytics provides objective photographic measurements only and does not diagnose hair loss or offer medical advice.</p>
      </main>
    </div>
  );
}
