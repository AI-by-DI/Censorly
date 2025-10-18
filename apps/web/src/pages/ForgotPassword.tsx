import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { useNavigate } from "react-router-dom";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [newPw, setNewPw] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null); // 🔎 ekrana bas
  const nav = useNavigate();

  const onSubmit = async () => {
    console.log("[FP] click"); // 🔎 tıklama kesin geldi mi?
    setLastError(null);

    if (!email.trim() || !newPw.trim()) {
      toast.error("E-posta ve yeni parola gerekli");
      setLastError("missing_fields");
      return;
    }

    try {
      setLoading(true);
      // ✅ Backend Form(...) bekliyor: FormData gönder
      const fd = new FormData();
      fd.append("email", email.trim());
      fd.append("new_password", newPw);

      console.log("[FP] posting to /reset-password", { email });
      const API_BASE = import.meta.env.VITE_API_URL;  // 🌍 ortamdan al
      const res = await axios.post(`${API_BASE}/auth/reset-password`, fd, {
        // baseURL’in yoksa proxy ile /api’yi backend’e yönlendiriyorsun
        // Vite proxy varsa ekstra ayar gerekmez
        headers: { /* FormData gönderince Content-Type otomatik ayarlanır */ },
        validateStatus: () => true, // 🔎 4xx/5xx yakalamak için
      });

      console.log("[FP] response", res.status, res.data);
      if (res.status === 200 && res.data?.detail === "password_reset_success") {
        toast.success("Parola güncellendi 🎉");
        nav("/login?tab=login", { replace: true });
        return;
      }

      const msg = res.data?.detail || `HTTP ${res.status}`;
      setLastError(String(msg));
      toast.error(String(msg));
    } catch (e: any) {
      console.error("[FP] error", e);
      const msg = e?.response?.data?.detail || e?.message || "request_failed";
      setLastError(String(msg));
      toast.error(String(msg));
    } finally {
      setLoading(false);
    }
  };

  // Enter tuşu ile gönderme
  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !loading) onSubmit();
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-card/90 p-8 rounded-2xl shadow-lg text-white">
        <h2 className="text-2xl font-bold mb-4 text-center">Parolanı Sıfırla</h2>

        <label className="text-sm text-muted-foreground">E-posta adresi</label>
        <Input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label="email"
        />

        <label className="text-sm text-muted-foreground mt-4 block">Yeni parola</label>
        <Input
          type="password"
          placeholder="••••••••"
          value={newPw}
          onChange={(e) => setNewPw(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label="new password"
        />

        <Button
          type="button"            // 🔒 submit değil, tıklamayı garanti et
          className="w-full mt-5"
          onClick={onSubmit}
          disabled={loading}
          aria-busy={loading}
          aria-label="submit new password"
        >
          {loading ? "Güncelleniyor..." : "Parolayı Güncelle"}
        </Button>

        {/* 🔎 Debug panel: ekranda son hatayı göster */}
        {lastError && (
          <div className="mt-4 text-xs text-red-300 break-words">
            Debug: {lastError}
          </div>
        )}
      </div>
    </div>
  );
}
