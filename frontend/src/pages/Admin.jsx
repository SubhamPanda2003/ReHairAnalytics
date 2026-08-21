import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import StatusPill from "@/components/StatusPill";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { ShieldCheck, Check, X, Loader2, Stethoscope, UserCog, Crown, Zap, Minus, Plus, Trash2 } from "lucide-react";

const ROLE_LABELS = {
  super_admin: ["Super admin", "bg-primary/15 text-primary"],
  admin: ["Admin", "bg-accent text-accent-foreground"],
  dermatologist: ["Dermatologist", "bg-amber-500/15 text-amber-600"],
  user: ["User", "bg-muted text-muted-foreground"],
};

/** One editable row in the "Scan credits" tab: report count (read-only) plus
 * a stepper + direct input for the per-user limit override. Blank = no
 * override (falls back to the global default set below). */
function ScanCreditRow({ row, onSave }) {
  const [value, setValue] = useState(row.scan_limit == null ? "" : String(row.scan_limit));
  const [saving, setSaving] = useState(false);

  const step = (delta) => {
    const base = value === "" ? (row.effective_limit ?? 0) : parseInt(value, 10) || 0;
    setValue(String(Math.max(0, base + delta)));
  };

  const save = async () => {
    setSaving(true);
    try {
      await onSave(row.user_id, value === "" ? null : parseInt(value, 10));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-3" data-testid={`credit-${row.user_id}`}>
      <div>
        <p className="font-medium">{row.name || row.email}</p>
        <p className="text-xs text-muted-foreground">{row.email}</p>
      </div>
      <div className="flex items-center gap-3">
        <Badge variant="secondary" className="rounded-full">{row.scan_count} report{row.scan_count === 1 ? "" : "s"}</Badge>
        <div className="flex items-center gap-1">
          <Button type="button" size="icon" variant="outline" className="rounded-full h-8 w-8" onClick={() => step(-1)}><Minus className="w-3.5 h-3.5" /></Button>
          <Input
            className="w-16 text-center rounded-full h-8"
            placeholder="∞"
            value={value}
            onChange={(e) => setValue(e.target.value.replace(/\D/g, ""))}
            data-testid={`credit-input-${row.user_id}`}
          />
          <Button type="button" size="icon" variant="outline" className="rounded-full h-8 w-8" onClick={() => step(1)}><Plus className="w-3.5 h-3.5" /></Button>
        </div>
        <Button size="sm" className="rounded-full" onClick={save} disabled={saving} data-testid={`credit-save-${row.user_id}`}>
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save"}
        </Button>
      </div>
    </div>
  );
}

export default function Admin() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const qc = useQueryClient();
  const isSuper = user?.role === "super_admin";
  const isAdmin = user?.role === "admin" || isSuper;
  const [dermToDelete, setDermToDelete] = useState(null);

  const { data: derms, isLoading } = useQuery({ queryKey: ["admin-derms"], queryFn: async () => (await api.get("/admin/dermatologists")).data, enabled: isAdmin });
  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: async () => (await api.get("/admin/users")).data, enabled: isSuper });
  const { data: scanUsage } = useQuery({ queryKey: ["admin-scan-usage"], queryFn: async () => (await api.get("/admin/scan-usage")).data, enabled: isAdmin });
  const { data: settings } = useQuery({ queryKey: ["admin-settings"], queryFn: async () => (await api.get("/admin/settings")).data, enabled: isAdmin });

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-background"><Navbar />
        <div className="max-w-md mx-auto text-center py-24 px-6">
          <ShieldCheck className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
          <h1 className="font-heading text-2xl font-bold">Admins only</h1>
          <p className="text-muted-foreground mt-2">You don't have permission to view this page.</p>
          <Button className="rounded-full mt-6" onClick={() => navigate("/dashboard")}>Back to dashboard</Button>
        </div>
      </div>
    );
  }

  const setStatus = async (uid, action) => {
    try { await api.post(`/admin/dermatologists/${uid}/${action}`); toast.success(`Dermatologist ${action}d`); qc.invalidateQueries({ queryKey: ["admin-derms"] }); }
    catch (e) { toast.error("Action failed"); }
  };
  const deleteDerm = async () => {
    const uid = dermToDelete.user_id;
    try {
      await api.delete(`/admin/dermatologists/${uid}`);
      toast.success(`${dermToDelete.name || "Dermatologist"} deleted`);
      qc.invalidateQueries({ queryKey: ["admin-derms"] });
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not delete dermatologist");
    } finally {
      setDermToDelete(null);
    }
  };
  const setRole = async (uid, role) => {
    try { await api.post(`/admin/users/${uid}/role`, { role }); toast.success(`Role set to ${role}`); qc.invalidateQueries({ queryKey: ["admin-users"] }); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not change role"); }
  };
  const saveScanLimit = async (uid, scan_limit) => {
    try {
      await api.post(`/admin/users/${uid}/scan-limit`, { scan_limit });
      toast.success("Scan limit updated");
      qc.invalidateQueries({ queryKey: ["admin-scan-usage"] });
    } catch (e) { toast.error(e.response?.data?.detail || "Could not update scan limit"); }
  };
  const saveSettings = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const limitRaw = fd.get("default_scan_limit");
    try {
      await api.post("/admin/settings", {
        default_scan_limit: limitRaw === "" ? null : parseInt(limitRaw, 10),
        whatsapp_number: fd.get("whatsapp_number"),
        exhausted_message: fd.get("exhausted_message"),
      });
      toast.success("Settings saved");
      qc.invalidateQueries({ queryKey: ["admin-settings"] });
    } catch (e) { toast.error(e.response?.data?.detail || "Could not save settings"); }
  };

  const pending = (derms || []).filter((d) => d.status === "pending");
  const others = (derms || []).filter((d) => d.status !== "pending");

  return (
    <div className="min-h-screen bg-background" data-testid="admin-page">
      <Navbar />
      <main className="max-w-5xl mx-auto px-5 md:px-8 py-8">
        <div className="flex items-center gap-2 mb-1">
          <h1 className="font-heading text-3xl font-bold tracking-tight">Admin</h1>
          {isSuper && <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-primary/15 text-primary"><Crown className="w-3.5 h-3.5" /> Super admin</span>}
        </div>
        <p className="text-muted-foreground mb-8">Approve dermatologists, manage scan credits{isSuper ? ", and manage user roles" : ""}.</p>

        <Tabs defaultValue="derms">
          <TabsList className="rounded-full h-auto p-1">
            <TabsTrigger value="derms" className="rounded-full" data-testid="tab-derms"><Stethoscope className="w-4 h-4 mr-1.5" /> Dermatologists</TabsTrigger>
            <TabsTrigger value="credits" className="rounded-full" data-testid="tab-credits"><Zap className="w-4 h-4 mr-1.5" /> Scan credits</TabsTrigger>
            {isSuper && <TabsTrigger value="users" className="rounded-full" data-testid="tab-users"><UserCog className="w-4 h-4 mr-1.5" /> Users</TabsTrigger>}
          </TabsList>

          <TabsContent value="derms" className="mt-6">
            {isLoading ? <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div> : (
              <>
                <h3 className="font-heading font-semibold mb-3">Pending approval ({pending.length})</h3>
                {pending.length === 0 ? <p className="text-muted-foreground text-sm mb-8">Nothing pending.</p> : (
                  <div className="space-y-3 mb-8">
                    {pending.map((d) => (
                      <div key={d.user_id} className="rounded-2xl border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-3" data-testid={`pending-${d.user_id}`}>
                        <div className="flex items-center gap-3">
                          {d.photo ? <img src={d.photo} alt="" className="w-11 h-11 rounded-xl object-cover" referrerPolicy="no-referrer" /> : <div className="w-11 h-11 rounded-xl bg-accent flex items-center justify-center"><Stethoscope className="w-5 h-5 text-accent-foreground" /></div>}
                          <div>
                            <p className="font-medium">{d.name} <span className="text-xs text-muted-foreground">· {d.specialty}</span></p>
                            <p className="text-xs text-muted-foreground">{d.email} · {d.years_experience || "?"} yrs · {d.price || "—"}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button size="sm" className="rounded-full" onClick={() => setStatus(d.user_id, "approve")} data-testid={`approve-${d.user_id}`}><Check className="w-4 h-4 mr-1" /> Approve</Button>
                          <Button size="sm" variant="outline" className="rounded-full" onClick={() => setStatus(d.user_id, "reject")} data-testid={`reject-${d.user_id}`}><X className="w-4 h-4 mr-1" /> Reject</Button>
                          <Button size="icon" variant="outline" className="rounded-full h-8 w-8 text-destructive hover:bg-destructive hover:text-destructive-foreground" onClick={() => setDermToDelete(d)} aria-label={`Delete ${d.name}`} data-testid={`delete-derm-${d.user_id}`}><Trash2 className="w-3.5 h-3.5" /></Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <h3 className="font-heading font-semibold mb-3">All dermatologists</h3>
                {others.length === 0 ? <p className="text-muted-foreground text-sm">None yet.</p> : (
                  <div className="space-y-3">
                    {others.map((d) => (
                      <div key={d.user_id} className="rounded-2xl border border-border bg-card p-4 flex items-center justify-between gap-3">
                        <div><p className="font-medium">{d.name} <span className="text-xs text-muted-foreground">· {d.specialty}</span></p><p className="text-xs text-muted-foreground">{d.email}</p></div>
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className="rounded-full capitalize">{d.status}</Badge>
                          {d.status !== "approved" && <Button size="sm" className="rounded-full" onClick={() => setStatus(d.user_id, "approve")}>Approve</Button>}
                          {d.status === "approved" && <Button size="sm" variant="outline" className="rounded-full" onClick={() => setStatus(d.user_id, "reject")}>Revoke</Button>}
                          <Button size="icon" variant="outline" className="rounded-full h-8 w-8 text-destructive hover:bg-destructive hover:text-destructive-foreground" onClick={() => setDermToDelete(d)} aria-label={`Delete ${d.name}`} data-testid={`delete-derm-${d.user_id}`}><Trash2 className="w-3.5 h-3.5" /></Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </TabsContent>

          <TabsContent value="credits" className="mt-6">
            {settings && (
              <form onSubmit={saveSettings} className="rounded-2xl border border-border bg-card p-4 mb-8 space-y-3" data-testid="settings-form">
                <h3 className="font-heading font-semibold">Global defaults</h3>
                <div className="grid sm:grid-cols-2 gap-3">
                  <label className="text-sm">
                    <span className="text-muted-foreground text-xs block mb-1">Default scan limit (blank = unlimited)</span>
                    <Input name="default_scan_limit" type="text" inputMode="numeric" defaultValue={settings.default_scan_limit ?? ""} placeholder="∞" />
                  </label>
                  <label className="text-sm">
                    <span className="text-muted-foreground text-xs block mb-1">WhatsApp number</span>
                    <Input name="whatsapp_number" type="text" defaultValue={settings.whatsapp_number} />
                  </label>
                </div>
                <label className="text-sm block">
                  <span className="text-muted-foreground text-xs block mb-1">Message shown when a user runs out of scans</span>
                  <Textarea name="exhausted_message" defaultValue={settings.exhausted_message} rows={2} />
                </label>
                <Button type="submit" size="sm" className="rounded-full">Save settings</Button>
              </form>
            )}

            <h3 className="font-heading font-semibold mb-3">Users</h3>
            {!scanUsage ? <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div> : (
              <div className="space-y-3">
                {scanUsage.map((row) => <ScanCreditRow key={row.user_id} row={row} onSave={saveScanLimit} />)}
              </div>
            )}
          </TabsContent>

          {isSuper && (
            <TabsContent value="users" className="mt-6">
              <div className="space-y-3">
                {(users || []).map((u) => (
                  <div key={u.user_id} className="rounded-2xl border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-3" data-testid={`user-${u.user_id}`}>
                    <div className="flex items-center gap-3">
                      {u.picture ? <img src={u.picture} alt="" className="w-9 h-9 rounded-full object-cover" referrerPolicy="no-referrer" /> : <div className="w-9 h-9 rounded-full bg-accent flex items-center justify-center text-xs font-semibold">{u.name?.[0] || "U"}</div>}
                      <div><p className="font-medium">{u.name || u.email}</p><p className="text-xs text-muted-foreground">{u.email}</p></div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusPill value={u.role} labels={ROLE_LABELS} />
                      {u.role !== "super_admin" && (u.role === "admin"
                        ? <Button size="sm" variant="outline" className="rounded-full" onClick={() => setRole(u.user_id, "user")} data-testid={`demote-${u.user_id}`}>Remove admin</Button>
                        : <Button size="sm" className="rounded-full" onClick={() => setRole(u.user_id, "admin")} data-testid={`promote-${u.user_id}`}>Make admin</Button>)}
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>
          )}
        </Tabs>
      </main>

      <AlertDialog open={!!dermToDelete} onOpenChange={(o) => !o && setDermToDelete(null)}>
        <AlertDialogContent className="rounded-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {dermToDelete?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes their profile from the directory and reverts their account back to a regular user.
              Any pending or confirmed appointments with them will be cancelled. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-full" data-testid="delete-derm-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={deleteDerm}
              className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="delete-derm-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
