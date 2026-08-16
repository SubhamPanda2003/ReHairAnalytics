import React, { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fileUrl } from "@/lib/api";
import { fmtScore } from "@/lib/scores";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Stethoscope, Clock, Check, X, Video, Loader2, Hourglass, BadgeCheck, History, ImageOff } from "lucide-react";

const empty = { name: "", specialty: "", years_experience: "", bio: "", photo: "", meeting_link: "", price: "" };

export default function DermPractice() {
  const { user, checkAuth } = useAuth();
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  const { data: profile, isLoading } = useQuery({ queryKey: ["derm-me"], queryFn: async () => (await api.get("/derm/me")).data });
  const { data: appts } = useQuery({ queryKey: ["appointments"], queryFn: async () => (await api.get("/appointments")).data });
  const incoming = appts?.as_dermatologist || [];

  const [historyApptId, setHistoryApptId] = useState(null);
  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ["appointment-history", historyApptId],
    queryFn: async () => (await api.get(`/appointments/${historyApptId}/history`)).data,
    enabled: !!historyApptId,
  });

  const hasProfile = profile && profile.name;

  useEffect(() => {
    if (hasProfile) setForm({ ...empty, ...profile, years_experience: profile.years_experience ?? "" });
  }, [hasProfile, profile]);

  const save = async () => {
    if (!form.name || !form.specialty || !form.meeting_link) { toast.error("Name, specialty and meeting link are required"); return; }
    setSaving(true);
    try {
      await api.post("/derm/register", {
        name: form.name, specialty: form.specialty,
        years_experience: form.years_experience ? parseInt(form.years_experience) : null,
        bio: form.bio, photo: form.photo, meeting_link: form.meeting_link, price: form.price,
      });
      toast.success(hasProfile ? "Profile updated" : "Submitted for approval");
      setEditing(false);
      await checkAuth();
      qc.invalidateQueries({ queryKey: ["derm-me"] });
    } catch (e) { toast.error("Could not save"); }
    setSaving(false);
  };

  const act = async (id, action) => {
    try {
      await api.post(`/appointments/${id}/${action}`);
      toast.success(`Appointment ${action}ed`);
      qc.invalidateQueries({ queryKey: ["appointments"] });
    } catch (e) { toast.error("Action failed"); }
  };

  const Field = ({ label, k, type = "text", placeholder, area }) => (
    <div>
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</Label>
      {area ? (
        <Textarea value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} placeholder={placeholder} className="mt-1.5 rounded-xl" data-testid={`derm-${k}`} />
      ) : (
        <Input type={type} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} placeholder={placeholder} className="mt-1.5 rounded-xl" data-testid={`derm-${k}`} />
      )}
    </div>
  );

  const showForm = !hasProfile || editing;

  return (
    <div className="min-h-screen bg-background" data-testid="derm-practice-page">
      <Navbar />
      <main className="max-w-4xl mx-auto px-5 md:px-8 py-8">
        <h1 className="font-heading text-3xl font-bold tracking-tight mb-1">My practice</h1>
        <p className="text-muted-foreground mb-8">Register as a dermatologist and manage consultation requests.</p>

        {isLoading ? (
          <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div>
        ) : (
          <>
            {hasProfile && (
              <div className={`rounded-2xl border p-4 mb-6 flex items-center gap-3 ${profile.status === "approved" ? "border-primary/30 bg-primary/10" : profile.status === "rejected" ? "border-destructive/30 bg-destructive/10" : "border-amber-500/30 bg-amber-500/10"}`} data-testid="derm-status">
                {profile.status === "approved" ? <BadgeCheck className="w-5 h-5 text-primary" /> : <Hourglass className="w-5 h-5 text-amber-600" />}
                <p className="text-sm font-medium">
                  {profile.status === "approved" ? "You're approved and visible to patients." : profile.status === "rejected" ? "Your application was not approved. You can edit and resubmit." : "Your application is pending admin approval."}
                </p>
                {!editing && <Button variant="outline" size="sm" className="rounded-full ml-auto" onClick={() => setEditing(true)} data-testid="edit-profile-btn">Edit profile</Button>}
              </div>
            )}

            {showForm ? (
              <div className="rounded-3xl border border-border bg-card p-6 md:p-8 mb-8">
                <h2 className="font-heading font-semibold text-lg mb-4">{hasProfile ? "Edit your profile" : "Register as a dermatologist"}</h2>
                <div className="grid sm:grid-cols-2 gap-4">
                  <Field label="Full name" k="name" placeholder="Dr. Jane Doe" />
                  <Field label="Specialty" k="specialty" placeholder="Trichologist / Dermatologist" />
                  <Field label="Years of experience" k="years_experience" type="number" placeholder="8" />
                  <Field label="Price / fees" k="price" placeholder="$60 / session" />
                  <Field label="Photo URL" k="photo" placeholder="https://…" />
                  <Field label="Meeting link (Google Meet)" k="meeting_link" placeholder="https://meet.google.com/…" />
                </div>
                <div className="mt-4"><Field label="Bio" k="bio" area placeholder="Short professional bio" /></div>
                <div className="flex gap-3 mt-6">
                  <Button onClick={save} disabled={saving} className="rounded-full" data-testid="derm-save-btn">{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : hasProfile ? "Save changes" : "Submit for approval"}</Button>
                  {editing && <Button variant="ghost" onClick={() => setEditing(false)} className="rounded-full">Cancel</Button>}
                </div>
              </div>
            ) : null}

            {profile?.status === "approved" && (
              <>
                <h2 className="font-heading text-xl font-semibold mb-4">Appointment requests</h2>
                {incoming.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No requests yet.</p>
                ) : (
                  <div className="space-y-3">
                    {incoming.map((a) => (
                      <div key={a.id} className="rounded-2xl border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-3" data-testid={`incoming-${a.id}`}>
                        <div>
                          <p className="font-medium">{a.patient_name || a.patient_email}</p>
                          <p className="text-xs text-muted-foreground flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> {new Date(a.requested_time).toLocaleString()}</p>
                          {a.note && <p className="text-sm text-muted-foreground mt-1">“{a.note}”</p>}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          {a.status === "requested" ? (
                            <>
                              <Button size="sm" className="rounded-full" onClick={() => act(a.id, "confirm")} data-testid={`confirm-${a.id}`}><Check className="w-4 h-4 mr-1" /> Confirm</Button>
                              <Button size="sm" variant="outline" className="rounded-full" onClick={() => act(a.id, "decline")} data-testid={`decline-${a.id}`}><X className="w-4 h-4 mr-1" /> Decline</Button>
                            </>
                          ) : a.status === "confirmed" ? (
                            <>
                              {a.share_history ? (
                                <Button size="sm" variant="outline" className="rounded-full" onClick={() => setHistoryApptId(a.id)} data-testid={`view-history-${a.id}`}>
                                  <History className="w-4 h-4 mr-1" /> View history
                                </Button>
                              ) : (
                                <span className="text-xs text-muted-foreground">Patient hasn't shared their history</span>
                              )}
                              <a href={a.meeting_link} target="_blank" rel="noreferrer"><Button size="sm" variant="outline" className="rounded-full"><Video className="w-4 h-4 mr-1" /> Meet link</Button></a>
                            </>
                          ) : <span className="text-xs text-muted-foreground capitalize">{a.status}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </main>

      <Dialog open={!!historyApptId} onOpenChange={(o) => !o && setHistoryApptId(null)}>
        <DialogContent className="rounded-3xl max-w-lg" data-testid="patient-history-dialog">
          <DialogHeader><DialogTitle className="font-heading">Shared history{history?.patient_name ? ` — ${history.patient_name}` : ""}</DialogTitle></DialogHeader>
          {historyLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
          ) : history ? (
            <div className="space-y-5">
              <p className="text-sm text-muted-foreground -mt-2">{history.patient_email}</p>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  ["Overall", history.progress?.latest?.overall],
                  ["Density", history.progress?.latest?.density],
                  ["Coverage", history.progress?.latest?.coverage],
                  ["Hairline", history.progress?.latest?.hairline],
                ].map(([label, val]) => (
                  <div key={label} className="rounded-xl border border-border bg-secondary/40 p-3 text-center">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
                    <p className="font-heading text-xl font-bold mt-0.5">{fmtScore(val)}</p>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-muted-foreground">
                <span>{history.progress?.streak ?? 0} scan{history.progress?.streak === 1 ? "" : "s"} logged</span>
                {history.progress?.days_since_last != null && <span>Last scan {history.progress.days_since_last === 0 ? "today" : `${history.progress.days_since_last}d ago`}</span>}
                {history.progress?.estimated_progress?.overall != null && (
                  <span>Overall {history.progress.estimated_progress.overall >= 0 ? "+" : ""}{history.progress.estimated_progress.overall} vs baseline</span>
                )}
              </div>

              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Most recent photos</p>
                {Object.keys(history.recent_photos || {}).length === 0 ? (
                  <p className="text-sm text-muted-foreground flex items-center gap-1.5"><ImageOff className="w-4 h-4" /> No photos yet</p>
                ) : (
                  <div className="grid grid-cols-3 gap-2">
                    {Object.entries(history.recent_photos).map(([region, path]) => (
                      <div key={region} className="rounded-xl overflow-hidden border border-border aspect-square relative" data-testid={`history-photo-${region}`}>
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
