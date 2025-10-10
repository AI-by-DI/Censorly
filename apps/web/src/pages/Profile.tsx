import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PreferenceForm, { PrefState } from "../components/PreferenceForm";
import { prefApi, ActiveProfile } from "../lib/api";
import { authApi } from "../lib/api";

const CATS = ["alcohol","blood","violence","nudity","clown","snake","spider"] as const;
type Cat = typeof CATS[number];

const EMPTY_PREF: PrefState = {
  name: "default",
  allow_map: { alcohol:true, blood:true, violence:true, nudity:true, clown:true, snake:true, spider:true } as Record<Cat, boolean>,
  mode: "blur",
  mode_map: {}
};

export default function ProfilePage(){
  const navigate = useNavigate();

  const [state, setState] = useState<PrefState>(EMPTY_PREF);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [justSaved, setJustSaved] = useState(false);

  // init: tek profil – yoksa oluştur, varsa doldur
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const items = await prefApi.list();
        if (!items.length) {
          const created = await prefApi.create(EMPTY_PREF);
          ActiveProfile.set(created.id);
          setState({
            name: (created.name ?? "default"),
            allow_map: withAllCats(created.allow_map || {}),
            mode: created.mode || "blur",
            mode_map: created.mode_map || {}
          });
        } else {
          const current = items[0]; // tek profil varsayımı
          ActiveProfile.set(current.id);
          setState({
            name: (current.name ?? "default"),
            allow_map: withAllCats(current.allow_map || {}),
            mode: current.mode || "blur",
            mode_map: current.mode_map || {}
          });
        }
      } catch (e) {
        console.error("Profile init error:", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const onSubmit = async () => {
    const activeId = ActiveProfile.get();
    if (!activeId) return;
    setSaving(true);
    try {
      const body = sanitizePayload(state);
      const updated = await prefApi.update(activeId, body);

      // formu backend’in döndürdüğü değerle senkronla
      setState({
        name: (updated.name ?? "default"),
        allow_map: withAllCats(updated.allow_map || {}),
        mode: updated.mode || "blur",
        mode_map: updated.mode_map || {}
      });

      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    } catch (e:any) {
      alert("Hata: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const onLogout = async () => {
    try { await authApi.logout(); } catch {}
    window.dispatchEvent(new Event("auth:changed"));
    navigate("/login", { replace: true });
  };

  // Form state'inden effective özetini hesapla (API çağrısı yok)
  const effective = useMemo(() => {
    const out: Record<Cat, "none" | "blur" | "skip"> = {} as any;
    for (const c of CATS) {
      const allow = state.allow_map[c] ?? true;
      out[c] = allow ? "none" : (state.mode_map[c] || state.mode || "blur");
    }
    return out;
  }, [state]);

  if (loading) return <div style={{padding:24}}>Yükleniyor…</div>;

  return (
    <div style={{padding:"24px"}}>
      <header style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16 }}>
        <h1 style={{ margin:0 }}>Profil Ayarları</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <Link to="/dashboard" style={{ textDecoration:"none", padding:"8px 12px", border:"1px solid #333", borderRadius:8 }}>
            Dashboard’a dön
          </Link>
          <button
            onClick={onLogout}
            style={{
              padding: "8px 12px",
              border: "1px solid #333",
              borderRadius: 8,
              background: "transparent",
              cursor: "pointer",
            }}
          >
            Çıkış
          </button>
        </div>
      </header>

      <PreferenceForm
        value={state}
        onChange={setState}
        onSubmit={onSubmit}
        submitting={saving}
      />

      {justSaved && (
        <div style={{ marginTop: 8, color: "#2e7d32" }}>✓ Kaydedildi</div>
      )}

      {/* Renkli özet rozetleri */}
      <section style={{ marginTop: 24 }}>
        <h3 style={{ marginTop: 0 }}>Tercih Özeti</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {CATS.map((cat) => (
            <Badge key={cat} label={labelOf(cat)} mode={effective[cat]} />
          ))}
        </div>
      </section>
    </div>
  );
}

function withAllCats(map: any): Record<Cat, boolean> {
  const out: any = {};
  for (const c of CATS) out[c] = map[c] ?? true;
  return out;
}

function sanitizePayload(s: PrefState) {
  const allow = {...s.allow_map};
  const mode_map: any = {};
  for (const c of CATS) {
    if (allow[c] === false) {
      mode_map[c] = s.mode_map[c] || s.mode || "blur";
    }
  }
  return {
    name: s.name || "default",
    allow_map: allow,
    mode: s.mode || "blur",
    mode_map
  };
}

function Badge({ label, mode }: { label: string; mode: "none" | "blur" | "skip" }) {
  const color = mode === "none" ? "#2e7d32" : mode === "blur" ? "#1976d2" : "#c62828";
  const bg    = mode === "none" ? "rgba(46,125,50,.15)" : mode === "blur" ? "rgba(25,118,210,.15)" : "rgba(198,40,40,.15)";
  const txt   = mode === "none" ? "dokunma" : mode === "blur" ? "bulanıklaştır" : "atla";
  return (
    <span style={{ padding: "6px 10px", borderRadius: 999, border: `1px solid ${color}`, background: bg, color }}>
      {label}: {txt}
    </span>
  );
}

function labelOf(cat: string) {
  switch (cat) {
    case "alcohol": return "Alkol";
    case "blood": return "Kan";
    case "violence": return "Şiddet";
    case "nudity": return "Mahremiyet";
    case "clown": return "Palyaço";
    case "snake": return "Yılan";
    case "spider": return "Örümcek";
    default: return cat;
  }
}
