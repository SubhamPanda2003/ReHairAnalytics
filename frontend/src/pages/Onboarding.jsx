import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Activity, ArrowRight } from "lucide-react";

export default function Onboarding() {
  const navigate = useNavigate();
  const { checkAuth } = useAuth();
  const [form, setForm] = useState({ age: "", gender: "", hair_type: "", treatment_status: "", goals: "", phone: "" });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/profile", {
        age: form.age ? parseInt(form.age) : null,
        gender: form.gender || null,
        hair_type: form.hair_type || null,
        treatment_status: form.treatment_status || null,
        goals: form.goals || null,
        phone: form.phone || null,
      });
      await checkAuth();
      toast.success("Profile created");
      navigate("/dashboard");
    } catch (e) {
      toast.error("Could not save profile");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-5 hair-grid-bg" data-testid="onboarding-page">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-lg rounded-3xl border border-border bg-card p-8 md:p-10 shadow-xl">
        <div className="w-11 h-11 rounded-xl bg-primary flex items-center justify-center mb-5">
          <Activity className="w-6 h-6 text-primary-foreground" />
        </div>
        <h1 className="font-heading text-2xl font-bold tracking-tight">Before we start tracking</h1>
        <p className="text-muted-foreground text-sm mt-1.5 mb-7">This is what lets us tell you whether what you're doing is actually working. Everything is optional.</p>

        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Age</Label>
              <Input type="number" value={form.age} onChange={(e) => setForm({ ...form, age: e.target.value })}
                placeholder="32" className="mt-1.5 rounded-xl" data-testid="onboarding-age" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">Gender</Label>
              <Select value={form.gender} onValueChange={(v) => setForm({ ...form, gender: v })}>
                <SelectTrigger className="mt-1.5 rounded-xl" data-testid="onboarding-gender"><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="male">Male</SelectItem>
                  <SelectItem value="female">Female</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                  <SelectItem value="prefer_not">Prefer not to say</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">Mobile / WhatsApp number</Label>
            <Input type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="+91 98765 43210" className="mt-1.5 rounded-xl" data-testid="onboarding-phone" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">Hair type</Label>
            <Select value={form.hair_type} onValueChange={(v) => setForm({ ...form, hair_type: v })}>
              <SelectTrigger className="mt-1.5 rounded-xl" data-testid="onboarding-hairtype"><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="straight">Straight</SelectItem>
                <SelectItem value="wavy">Wavy</SelectItem>
                <SelectItem value="curly">Curly</SelectItem>
                <SelectItem value="coily">Coily</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">What are you currently doing about it?</Label>
            <Select value={form.treatment_status} onValueChange={(v) => setForm({ ...form, treatment_status: v })}>
              <SelectTrigger className="mt-1.5 rounded-xl" data-testid="onboarding-treatment"><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Nothing yet</SelectItem>
                <SelectItem value="minoxidil">Minoxidil</SelectItem>
                <SelectItem value="finasteride">Finasteride</SelectItem>
                <SelectItem value="prp">PRP / clinical treatment</SelectItem>
                <SelectItem value="multiple">Multiple treatments</SelectItem>
                <SelectItem value="prefer_not">Prefer not to say</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">Your goals</Label>
            <Textarea value={form.goals} onChange={(e) => setForm({ ...form, goals: e.target.value })}
              placeholder="e.g. Monitor crown density over 6 months" className="mt-1.5 rounded-xl" data-testid="onboarding-goals" />
          </div>
        </div>

        <Button onClick={save} disabled={saving} className="w-full mt-8 rounded-full h-11" data-testid="onboarding-submit">
          {saving ? "Saving…" : <>Continue to dashboard <ArrowRight className="w-4 h-4 ml-1" /></>}
        </Button>
      </motion.div>
    </div>
  );
}
