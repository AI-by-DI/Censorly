import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Header from "../components/Header";
import FilterToggle, { FilterMode } from "../components/FilterToggle";
import { Button } from "../components/ui/button";
import { Save, RotateCcw } from "lucide-react";
import { prefApi, ActiveProfile } from "../lib/api";
import { authApi } from "../lib/api";
import { Flame, Droplet, Wine, Eye, Smile, Worm, Bug } from "lucide-react";

const CATS = ["alcohol", "blood", "violence", "nudity", "clown", "snake", "spider"] as const;
type Cat = typeof CATS[number];

const EMPTY_PREF = {
  name: "default",
  mode: "blur" as const,
  mode_map: {
    alcohol: "none",
    blood: "none",
    violence: "none",
    nudity: "none",
    clown: "none",
    snake: "none",
    spider: "none",
  } as Record<Cat, FilterMode>,
};

export default function ProfilePage() {
  const navigate = useNavigate();
  const [state, setState] = useState(EMPTY_PREF);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [justSaved, setJustSaved] = useState(false);

  // ✅ Backend'den mevcut tercihleri (effective modları) yükle
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const profiles = await prefApi.list();
        if (!profiles.length) {
          const created = await prefApi.create(EMPTY_PREF);
          ActiveProfile.set(created.id);
          setState(fillAllCats(created));
        } else {
          const current = profiles[0];
          ActiveProfile.set(current.id);

          // 🔥 Effective modları backend'den al
          const eff = await prefApi.effective(current.id);
          const effectiveModes = eff.effective;

          // 🔥 State'i güncelle
          setState({
            ...fillAllCats(current),
            mode_map: effectiveModes,
          });
        }
      } catch (e) {
        console.error("Profile init error:", e);
        toast.error("Failed to load preferences");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleChangeMode = (key: Cat, mode: FilterMode) => {
    setState((prev) => ({
      ...prev,
      mode_map: { ...prev.mode_map, [key]: mode },
    }));
  };

  const handleSave = async () => {
    const activeId = ActiveProfile.get();
    if (!activeId) return;
    setSaving(true);
    try {
      const body = sanitizePayload(state);
      await prefApi.update(activeId, body);
      toast.success("Filter preferences saved successfully!");
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    } catch (e: any) {
      toast.error("Failed to save preferences: " + e.message);
    } finally {
      setSaving(false);
    }
  };



  const handleReset = () => {
    setState(EMPTY_PREF);
    toast.info("Preferences reset to defaults");
  };

  const onLogout = async () => {
    try {
      await authApi.logout();
    } catch {}
    window.dispatchEvent(new Event("auth:changed"));
    navigate("/login", { replace: true });
  };

  const filterCategories = [
    { key: "violence" as const, name: "Violence", icon: Flame, color: "hsl(4, 100%, 60%)" },
    { key: "blood" as const, name: "Blood", icon: Droplet, color: "hsl(270, 100%, 74%)" },
    { key: "alcohol" as const, name: "Alcohol", icon: Wine, color: "hsl(165, 100%, 36%)" },
    { key: "nudity" as const, name: "Nudity", icon: Eye, color: "hsl(33, 100%, 56%)" },
    { key: "clown" as const, name: "Clown (Phobia)", icon: Smile, color: "hsl(49, 100%, 52%)" },
    { key: "snake" as const, name: "Snake (Phobia)", icon: Worm, color: "hsl(28, 30%, 56%)" },
    { key: "spider" as const, name: "Spider (Phobia)", icon: Bug, color: "hsl(210, 7%, 46%)" },
  ];

  if (loading)
    return <div className="flex justify-center items-center min-h-screen">Loading preferences...</div>;

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="container mx-auto px-8 pt-32 pb-16">
        <div className="max-w-4xl mx-auto space-y-8 animate-fade-in">
          {/* Header */}
          <div className="flex justify-between items-center">
            <div className="space-y-2">
              <h1 className="text-4xl font-bold">Profile & Preferences</h1>
              <p className="text-muted-foreground text-lg">
                Customize your content filtering preferences for a safer viewing experience.
              </p>
            </div>
            <Button variant="outline" onClick={onLogout}>
              Logout
            </Button>
          </div>

          {/* Preferences */}
          <div className="space-y-4">
            <h2 className="text-2xl font-semibold">My Filter Preferences</h2>
            <div className="grid gap-4">
              {filterCategories.map((cat) => (
                <FilterToggle
                  key={cat.key}
                  name={cat.name}
                  icon={cat.icon}
                  color={cat.color}
                  mode={state.mode_map[cat.key]}
                  onChange={(m) => handleChangeMode(cat.key, m)}
                />
              ))}
            </div>
          </div>

          {/* Buttons */}
          <div className="flex gap-4">
            <Button size="lg" onClick={handleSave} disabled={saving}>
              <Save className="w-5 h-5 mr-2" />
              {saving ? "Saving..." : "Save Preferences"}
            </Button>
            <Button size="lg" variant="outline" onClick={handleReset}>
              <RotateCcw className="w-5 h-5 mr-2" />
              Reset Defaults
            </Button>
          </div>

          {justSaved && <div className="text-green-600">✓ Preferences saved successfully!</div>}
        </div>
      </div>
    </div>
  );
}

// ✅ backend verisini normalize eder
function fillAllCats(data: any) {
  const mode_map: any = {};
  for (const c of CATS) mode_map[c] = data.mode_map?.[c] ?? "none";
  return { ...EMPTY_PREF, ...data, mode_map };
}

// ✅ Kaydetme öncesi backend'e uygun formata çevirir
function sanitizePayload(s: any) {
  const allow_map: Record<string, boolean> = {};
  const mode_map: Record<string, "blur" | "skip"> = {};

  for (const [cat, mode] of Object.entries(s.mode_map || {})) {
    if (mode === "none") {
      allow_map[cat] = true; // filtre yok
    } else {
      allow_map[cat] = false; // filtre aktif
      mode_map[cat] = mode as "blur" | "skip";
    }
  }

  return {
    name: s.name || "default",
    mode: s.mode || "blur",
    allow_map,
    mode_map,
  };
}


