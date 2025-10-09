import { useMemo, useState, useCallback } from "react";
import { authApi } from "../lib/api";
import CountrySelect from "./CountrySelect";

interface Props { onSuccess?: () => void; }

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function RegisterForm({ onSuccess }: Props) {
  const [email, setEmail] = useState<string>("");
  const [pw, setPw] = useState<string>("");
  const [country, setCountry] = useState<string | null>(null); // ISO-2
  const [age, setAge] = useState<number | "">("");
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const ages = useMemo(() => Array.from({ length: 100 }, (_, i) => i + 1), []);

  const validate = useCallback((): string | null => {
    const e = email.trim();
    if (!e) return "E-posta gerekli";
    if (!emailRe.test(e)) return "Geçerli bir e-posta girin";
    if (pw.length < 8) return "Parola en az 8 karakter olmalı";
    return null;
  }, [email, pw]);

  const submit = async () => {
    if (loading) return;
    setMsg(null);

    const v = validate();
    if (v) { setMsg(v); return; }

    try {
      setLoading(true);
      await authApi.register(
        email.trim(),
        pw,
        country,                         // "TR" | null
        age === "" ? null : Number(age)  // 1..100 | null
      );
      setMsg("Kayıt başarılı ✓ şimdi giriş yapabilirsiniz");
      onSuccess?.();
    } catch (e: any) {
      const d = e?.response?.data;
      setMsg(
        d?.detail === "email_in_use"
          ? "Bu e-posta zaten kayıtlı"
          : (typeof d?.detail === "string" ? d.detail : "Kayıt başarısız")
      );
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLDivElement> = (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); submit(); }
  };

  return (
    <div style={{ display:"grid", gap:10 }} onKeyDown={onKeyDown}>
      <label>E-posta</label>
      <input
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        inputMode="email"
        autoComplete="email"
        style={{ padding: 8 }}
      />

      <label>Parola</label>
      <input
        type="password"
        value={pw}
        onChange={(e) => setPw(e.target.value)}
        placeholder="En az 8 karakter"
        autoComplete="new-password"
        style={{ padding: 8 }}
      />

      <label>Ülke (opsiyonel)</label>
      <CountrySelect value={country} onChange={setCountry} />

      <label>Yaş (opsiyonel)</label>
      <select
        value={age}
        onChange={(e) => setAge(e.target.value === "" ? "" : Number(e.target.value))}
        style={{ padding: 8 }}
      >
        <option value="">Seçiniz</option>
        {ages.map((a) => <option key={a} value={a}>{a}</option>)}
      </select>

      <div style={{ display:"flex", gap:8, alignItems:"center", marginTop:6 }}>
        <button onClick={submit} disabled={loading}>
          {loading ? "Kaydediliyor..." : "Kayıt Ol"}
        </button>
        {msg && <span style={{ color: msg.includes("başarılı") ? "green" : "#c33" }}>{msg}</span>}
      </div>
    </div>
  );
}
