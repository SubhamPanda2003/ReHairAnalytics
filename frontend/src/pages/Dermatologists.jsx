import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import StatusPill from "@/components/StatusPill";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Stethoscope, Video, Clock, BadgeCheck, Loader2, CalendarPlus, ExternalLink, UserPlus, Share2, ShieldOff } from "lucide-react";

const APPOINTMENT_STATUS_LABELS = {
  requested: ["Requested", "bg-amber-500/15 text-amber-600"],
  confirmed: ["Confirmed", "bg-primary/15 text-primary"],
  declined: ["Declined", "bg-destructive/15 text-destructive"],
  cancelled: ["Cancelled", "bg-muted text-muted-foreground"],
};

export default function Dermatologists() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [selected, setSelected] = useState(null);
  const [when, setWhen] = useState("");
  const [note, setNote] = useState("");
  const [shareHistory, setShareHistory] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sharingId, setSharingId] = useState(null);

  const { data: derms, isLoading } = useQuery({ queryKey: ["dermatologists"], queryFn: async () => (await api.get("/dermatologists")).data });
  const { data: appts } = useQuery({ queryKey: ["appointments"], queryFn: async () => (await api.get("/appointments")).data });
  const myRequests = appts?.as_patient || [];

  const request = async () => {
    if (!when) { toast.error("Pick a date & time"); return; }
    setSubmitting(true);
    try {
      await api.post("/appointments", { dermatologist_id: selected.user_id, requested_time: when, note, share_history: shareHistory });
      toast.success("Request sent");
      setSelected(null); setWhen(""); setNote(""); setShareHistory(false);
      qc.invalidateQueries({ queryKey: ["appointments"] });
    } catch (e) { toast.error(e.response?.data?.detail || "Could not request"); }
    setSubmitting(false);
  };

  const toggleShare = async (appt) => {
    setSharingId(appt.id);
    try {
      await api.post(`/appointments/${appt.id}/${appt.share_history ? "unshare" : "share"}`);
      toast.success(appt.share_history ? "Stopped sharing your history" : "Your scan history is now shared for this appointment");
      qc.invalidateQueries({ queryKey: ["appointments"] });
    } catch (e) { toast.error("Could not update sharing"); }
    setSharingId(null);
  };

  const isDerm = user?.role === "dermatologist";

  return (
    <div className="min-h-screen bg-background" data-testid="dermatologists-page">
      <Navbar />
      <main className="max-w-6xl mx-auto px-5 md:px-8 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight">Consult a dermatologist</h1>
            <p className="text-muted-foreground mt-1">Book a video call to review your progress. Not an emergency service.</p>
          </div>
          {!isDerm && (
            <Button variant="outline" className="rounded-full" onClick={() => navigate("/derm")} data-testid="become-derm-btn">
              <UserPlus className="w-4 h-4 mr-1.5" /> Become a dermatologist
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div>
        ) : (derms?.length || 0) === 0 ? (
          <div className="rounded-2xl border border-border bg-card p-12 text-center">
            <Stethoscope className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No dermatologists are available yet. Check back soon.</p>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 mb-12">
            {derms.map((d, i) => (
              <motion.div key={d.user_id} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                className="rounded-2xl border border-border bg-card p-6" data-testid={`derm-card-${d.user_id}`}>
                <div className="flex items-center gap-3 mb-3">
                  {d.photo ? <img src={d.photo} alt={d.name} className="w-14 h-14 rounded-2xl object-cover" referrerPolicy="no-referrer" /> : <div className="w-14 h-14 rounded-2xl bg-accent flex items-center justify-center"><Stethoscope className="w-6 h-6 text-accent-foreground" /></div>}
                  <div>
                    <p className="font-heading font-semibold flex items-center gap-1">{d.name} <BadgeCheck className="w-4 h-4 text-primary" /></p>
                    <p className="text-sm text-muted-foreground">{d.specialty}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap mb-3">
                  {d.years_experience ? <Badge variant="secondary" className="rounded-full">{d.years_experience} yrs exp</Badge> : null}
                  {d.price ? <Badge variant="secondary" className="rounded-full">{d.price}</Badge> : null}
                </div>
                {d.bio && <p className="text-sm text-muted-foreground leading-relaxed line-clamp-3 mb-4">{d.bio}</p>}
                <Button className="w-full rounded-full" onClick={() => setSelected(d)} data-testid={`request-${d.user_id}`}>
                  <CalendarPlus className="w-4 h-4 mr-1.5" /> Request appointment
                </Button>
              </motion.div>
            ))}
          </div>
        )}

        {/* My requests */}
        <h2 className="font-heading text-xl font-semibold mb-4">My appointments</h2>
        {myRequests.length === 0 ? (
          <p className="text-muted-foreground text-sm">No appointments yet.</p>
        ) : (
          <div className="space-y-3">
            {myRequests.map((a) => (
              <div key={a.id} className="rounded-2xl border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-3" data-testid={`appt-${a.id}`}>
                <div>
                  <p className="font-medium">{a.derm_name}</p>
                  <p className="text-xs text-muted-foreground flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> {new Date(a.requested_time).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                  <StatusPill value={a.status} labels={APPOINTMENT_STATUS_LABELS} />
                  {["requested", "confirmed"].includes(a.status) && (
                    <Button
                      size="sm" variant={a.share_history ? "secondary" : "outline"} className="rounded-full"
                      disabled={sharingId === a.id} onClick={() => toggleShare(a)} data-testid={`toggle-share-${a.id}`}
                    >
                      {sharingId === a.id ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : a.share_history ? <ShieldOff className="w-3.5 h-3.5 mr-1.5" /> : <Share2 className="w-3.5 h-3.5 mr-1.5" />}
                      {a.share_history ? "Stop sharing history" : "Share history"}
                    </Button>
                  )}
                  {a.status === "confirmed" && a.meeting_link && (
                    <a href={a.meeting_link} target="_blank" rel="noreferrer" data-testid={`join-${a.id}`}>
                      <Button size="sm" className="rounded-full"><Video className="w-4 h-4 mr-1.5" /> Join <ExternalLink className="w-3.5 h-3.5 ml-1" /></Button>
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="rounded-3xl" data-testid="request-dialog">
          <DialogHeader><DialogTitle className="font-heading">Request appointment — {selected?.name}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Preferred date & time</Label>
              <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="mt-1.5 rounded-xl" data-testid="appt-datetime" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Note (optional)</Label>
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What would you like to discuss?" className="mt-1.5 rounded-xl" data-testid="appt-note" />
            </div>
            <label className="flex items-start gap-2.5 rounded-xl border border-border p-3 cursor-pointer" data-testid="appt-share-history-label">
              <Checkbox checked={shareHistory} onCheckedChange={(v) => setShareHistory(!!v)} className="mt-0.5" data-testid="appt-share-history" />
              <span className="text-sm">
                <span className="font-medium">Share my scan history with this dermatologist</span>
                <span className="block text-xs text-muted-foreground mt-0.5">They'll see your score trend and recent photos once the appointment is confirmed — only for this appointment, and you can turn it off anytime.</span>
              </span>
            </label>
          </div>
          <DialogFooter>
            <Button onClick={request} disabled={submitting} className="rounded-full w-full" data-testid="appt-submit">
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send request"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
