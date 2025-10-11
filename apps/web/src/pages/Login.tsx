import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../lib/api";
import RegisterForm from "../components/RegisterForm";

export default function Login() {
  const nav = useNavigate();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onLogin = async () => {
    setMsg(null);
    if (!email.trim() || !pw) return setMsg("E-posta ve parola gerekli");
    try {
      setLoading(true);
      await authApi.login(email.trim(), pw);
      nav("/dashboard");
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || "Giriş başarısız");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 420, margin: "80px auto", fontFamily: "system-ui" }}>
      <h2>Censorly • Hesap</h2>

      <div style={{ display:"flex", gap:8, margin:"12px 0" }}>
        <button onClick={() => setTab("login")}    style={{ background: tab==="login" ? "#4c7dff" : "#2c385f", color:"#fff", border:0, borderRadius:8, padding:"8px 12px" }}>Giriş</button>
        <button onClick={() => setTab("register")} style={{ background: tab==="register" ? "#4c7dff" : "#2c385f", color:"#fff", border:0, borderRadius:8, padding:"8px 12px" }}>Kayıt Ol</button>
      </div>

      {tab === "login" ? (
        <div style={{ display:"grid", gap:10 }}>
          <label>E-posta</label>
          <input value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" />
          <label>Parola</label>
          <input type="password" value={pw} onChange={e=>setPw(e.target.value)} placeholder="••••••••" />
          <div style={{ display:"flex", gap:8, alignItems:"center" }}>
            <button onClick={onLogin} disabled={loading}>{loading ? "Giriş yapılıyor..." : "Giriş"}</button>
            {msg && <span style={{ color:"#c33" }}>{msg}</span>}
          </div>
        </div>
      ) : (
        <RegisterForm onSuccess={() => { setTab("login"); setMsg("Kayıt başarılı, şimdi giriş yapın."); }} />
      )}
    </div>
  );
}
