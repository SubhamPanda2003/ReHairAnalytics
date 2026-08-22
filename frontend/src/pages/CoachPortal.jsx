import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, fileUrl } from "@/lib/api";
import { fmtScore } from "@/lib/scores";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Users, Loader2, ImageOff, FileText } from "lucide-react";

export default function CoachPortal() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: patients, isLoading } = useQuery({
    queryKey: ["coach-patients"],
    queryFn: async () => (await api.get("/coach/patients")).data,
    enabled: user?.role === "coach",
  });
  const [openPatientId, setOpenPatientId] = useState(null);
  const { data: report, isLoading: reportLoading } = useQuery({
    queryKey: ["coach-report", openPatientId],
    queryFn: async () => (await api.get(`/coach/patients/${openPatientId}/report`)).data,
    enabled: !!openPatientId,
  });

  if (user?.role !== "coach") {
    return (
      <div className="min-h-screen bg-background"><Navbar />
        <div className="max-w-md mx-auto text-center py-24 px-6">
          <Users className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
          <h1 className="font-heading text-2xl font-bold">Coaches only</h1>
          <p className="text-muted-foreground mt-2">You don't have permission to view this page.</p>
          <Button className="rounded-full mt-6" onClick={() => navigate("/dashboard")}>Back to dashboard</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background" data-testid="coach-portal-page">
      <Navbar />
      <main className="max-w-4xl mx-auto px-5 md:px-8 py-8">
        <h1 className="font-heading text-3xl font-bold tracking-tight mb-1">Your patients</h1>
        <p className="text-muted-foreground mb-8">Users who've chosen to share their reports with you.</p>

        {isLoading ? (
          <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div>
        ) : (patients || []).length === 0 ? (
          <p className="text-muted-foreground text-sm">No one has shared their reports with you yet.</p>
        ) : (
          <div className="space-y-3">
            {patients.map((p) => (
              <div key={p.user_id} className="rounded-2xl border border-border bg-card p-4 flex items-center justify-between gap-3" data-testid={`patient-${p.user_id}`}>
                <div><p className="font-medium">{p.name || p.email}</p><p className="text-xs text-muted-foreground">{p.email}</p></div>
                <Button size="sm" variant="outline" className="rounded-full" onClick={() => setOpenPatientId(p.user_id)} data-testid={`view-report-${p.user_id}`}>
                  <FileText className="w-4 h-4 mr-1" /> View report
                </Button>
              </div>
            ))}
          </div>
        )}
      </main>

      <Dialog open={!!openPatientId} onOpenChange={(o) => !o && setOpenPatientId(null)}>
        <DialogContent className="rounded-3xl max-w-lg" data-testid="coach-report-dialog">
          <DialogHeader><DialogTitle className="font-heading">Report{report?.patient_name ? ` — ${report.patient_name}` : ""}</DialogTitle></DialogHeader>
          {reportLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
          ) : report ? (
            <div className="space-y-5">
              <p className="text-sm text-muted-foreground -mt-2">{report.patient_email}</p>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  ["Overall", report.progress?.latest?.overall],
                  ["Density", report.progress?.latest?.density],
                  ["Coverage", report.progress?.latest?.coverage],
                  ["Hairline", report.progress?.latest?.hairline],
                ].map(([label, val]) => (
                  <div key={label} className="rounded-xl border border-border bg-secondary/40 p-3 text-center">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
                    <p className="font-heading text-xl font-bold mt-0.5">{fmtScore(val)}</p>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-muted-foreground">
                <span>{report.progress?.streak ?? 0} scan{report.progress?.streak === 1 ? "" : "s"} logged</span>
                {report.progress?.days_since_last != null && <span>Last scan {report.progress.days_since_last === 0 ? "today" : `${report.progress.days_since_last}d ago`}</span>}
                {report.progress?.estimated_progress?.overall != null && (
                  <span>Overall {report.progress.estimated_progress.overall >= 0 ? "+" : ""}{report.progress.estimated_progress.overall} vs baseline</span>
                )}
              </div>

              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Most recent photos</p>
                {Object.keys(report.recent_photos || {}).length === 0 ? (
                  <p className="text-sm text-muted-foreground flex items-center gap-1.5"><ImageOff className="w-4 h-4" /> No photos yet</p>
                ) : (
                  <div className="grid grid-cols-3 gap-2">
                    {Object.entries(report.recent_photos).map(([region, path]) => (
                      <div key={region} className="rounded-xl overflow-hidden border border-border aspect-square relative" data-testid={`report-photo-${region}`}>
                        <img src={fileUrl(path)} alt={region} className="w-full h-full object-cover" />
                        <span className="absolute bottom-1 left-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-black/60 text-white capitalize">{region}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
