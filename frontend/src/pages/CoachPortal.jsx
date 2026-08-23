import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fileUrl } from "@/lib/api";
import { fmtScore } from "@/lib/scores";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Users, Loader2, ImageOff, FileText, Flag } from "lucide-react";

const METRICS = [
  { value: "density", label: "Density" },
  { value: "coverage", label: "Coverage" },
  { value: "hairline", label: "Hairline" },
  { value: "overall", label: "Overall" },
];

export default function CoachPortal() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
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
  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ["coach-patient-timeline", openPatientId],
    queryFn: async () => (await api.get(`/coach/patients/${openPatientId}/timeline`)).data,
    enabled: !!openPatientId,
  });

  const [drafts, setDrafts] = useState({}); // session_id -> draft text
  const [posting, setPosting] = useState(null); // session_id currently being posted

  const addNote = async (sessionId) => {
    const text = (drafts[sessionId] || "").trim();
    if (!text) return;
    setPosting(sessionId);
    try {
      await api.post(`/coach/patients/${openPatientId}/sessions/${sessionId}/notes`, { text });
      setDrafts((d) => ({ ...d, [sessionId]: "" }));
      qc.invalidateQueries({ queryKey: ["coach-patient-timeline", openPatientId] });
      toast.success("Comment added");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not add comment");
    } finally {
      setPosting(null);
    }
  };

  // session_id -> { metric, value } -- the structured "flag this score" form,
  // separate from the free-text comment draft above.
  const [correctionDrafts, setCorrectionDrafts] = useState({});
  const [flagging, setFlagging] = useState(null);

  const setCorrectionField = (sessionId, field, value) =>
    setCorrectionDrafts((d) => ({ ...d, [sessionId]: { metric: "overall", value: "", ...d[sessionId], [field]: value } }));

  const addCorrection = async (sessionId) => {
    const draft = correctionDrafts[sessionId] || { metric: "overall", value: "" };
    if (draft.value === "" || Number.isNaN(Number(draft.value))) return;
    setFlagging(sessionId);
    try {
      await api.post(`/coach/patients/${openPatientId}/sessions/${sessionId}/corrections`, {
        metric: draft.metric, corrected_value: Number(draft.value),
      });
      setCorrectionDrafts((d) => ({ ...d, [sessionId]: { metric: draft.metric, value: "" } }));
      qc.invalidateQueries({ queryKey: ["coach-patient-timeline", openPatientId] });
      toast.success("Score flagged");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not flag score");
    } finally {
      setFlagging(null);
    }
  };

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
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-3">Timeline & comments</p>
                {sessionsLoading ? (
                  <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-primary" /></div>
                ) : (sessions || []).length === 0 ? (
                  <p className="text-sm text-muted-foreground flex items-center gap-1.5"><ImageOff className="w-4 h-4" /> No scans yet</p>
                ) : (
                  <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
                    {[...sessions].reverse().map((s) => (
                      <div key={s.id} className="rounded-xl border border-border bg-secondary/30 p-3" data-testid={`coach-session-${s.id}`}>
                        <div className="flex items-center gap-3 mb-2">
                          {s.images?.[0] ? (
                            <img src={fileUrl(s.images[0].thumb_path)} alt="" className="w-10 h-10 rounded-lg object-cover shrink-0" />
                          ) : (
                            <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center shrink-0"><ImageOff className="w-4 h-4 text-muted-foreground" /></div>
                          )}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium">{new Date(s.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</p>
                            {s.analysis ? (
                              <p className="text-xs text-muted-foreground">Density {fmtScore(s.analysis.density_score)} · Coverage {fmtScore(s.analysis.coverage_score)} · Overall {fmtScore(s.analysis.overall_score)}</p>
                            ) : <p className="text-xs text-muted-foreground">Not analyzed</p>}
                          </div>
                        </div>

                        {(s.coach_corrections || []).length > 0 && (
                          <div className="space-y-1.5 mb-2">
                            {s.coach_corrections.map((c) => (
                              <div key={c.id} className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-1.5 text-sm" data-testid={`coach-correction-${c.id}`}>
                                <p className="capitalize">
                                  <span className="font-medium">{c.metric}:</span>{" "}
                                  <span className="text-muted-foreground">AI said {c.ai_value ?? "—"}</span> → <span className="font-semibold">{c.corrected_value}</span>
                                </p>
                                {c.note && <p className="text-xs text-muted-foreground mt-0.5">{c.note}</p>}
                              </div>
                            ))}
                          </div>
                        )}

                        {(s.coach_notes || []).length > 0 && (
                          <div className="space-y-1.5 mb-2">
                            {s.coach_notes.map((n) => (
                              <div key={n.id} className="rounded-lg bg-card border border-border px-3 py-1.5 text-sm" data-testid={`coach-note-${n.id}`}>
                                <p>{n.text}</p>
                                <p className="text-[10px] text-muted-foreground mt-0.5">{n.coach_name || "Coach"} · {new Date(n.created_at).toLocaleDateString()}</p>
                              </div>
                            ))}
                          </div>
                        )}

                        {s.analysis && (
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <Select
                              value={correctionDrafts[s.id]?.metric || "overall"}
                              onValueChange={(v) => setCorrectionField(s.id, "metric", v)}
                            >
                              <SelectTrigger className="w-28 h-8 rounded-full text-xs" data-testid={`correction-metric-${s.id}`}><SelectValue /></SelectTrigger>
                              <SelectContent>
                                {METRICS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                              </SelectContent>
                            </Select>
                            <Input
                              type="number"
                              value={correctionDrafts[s.id]?.value ?? ""}
                              onChange={(e) => setCorrectionField(s.id, "value", e.target.value)}
                              placeholder="Correct value"
                              className="w-28 h-8 rounded-full text-xs text-center"
                              data-testid={`correction-value-${s.id}`}
                            />
                            <Button
                              size="sm" variant="outline" className="rounded-full h-8 shrink-0"
                              disabled={flagging === s.id || (correctionDrafts[s.id]?.value ?? "") === ""}
                              onClick={() => addCorrection(s.id)}
                              data-testid={`correction-submit-${s.id}`}
                            >
                              {flagging === s.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <><Flag className="w-3.5 h-3.5 mr-1" /> Flag</>}
                            </Button>
                          </div>
                        )}

                        <div className="flex items-center gap-2">
                          <Textarea
                            value={drafts[s.id] || ""}
                            onChange={(e) => setDrafts((d) => ({ ...d, [s.id]: e.target.value }))}
                            placeholder="Add a comment on this scan…"
                            className="rounded-xl text-sm min-h-9 h-9 py-2 resize-none"
                            data-testid={`coach-note-input-${s.id}`}
                          />
                          <Button
                            size="sm" className="rounded-full shrink-0"
                            disabled={posting === s.id || !(drafts[s.id] || "").trim()}
                            onClick={() => addNote(s.id)}
                            data-testid={`coach-note-submit-${s.id}`}
                          >
                            {posting === s.id ? <Loader2 className="w-4 h-4 animate-spin" /> : "Post"}
                          </Button>
                        </div>
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
