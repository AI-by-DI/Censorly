import { useState, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../lib/api";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { toast } from "sonner";
import { countryOptions } from "../lib/worldCountries";

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function RegisterForm({
  onSuccess,
}: {
  onSuccess?: () => void;
}) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [country, setCountry] = useState<string | null>(null);
  const [birthYear, setBirthYear] = useState<string | "">("");
  const [loading, setLoading] = useState(false);

  const years = useMemo(
    () => Array.from({ length: 101 }, (_, i) => 2025 - i).filter((y) => y >= 1925),
    []
  );

  const validate = useCallback((): string | null => {
    if (!email.trim()) return "E-posta gerekli";
    if (!emailRe.test(email.trim())) return "Geçerli bir e-posta girin";
    if (pw.length < 8) return "Parola en az 8 karakter olmalı";
    return null;
  }, [email, pw]);

  const submit = async () => {
    if (loading) return;
    const v = validate();
    if (v) {
      toast.error(v);
      return;
    }

    try {
      setLoading(true);
      await authApi.register(
        email.trim(),
        pw,
        country,
        birthYear ? Number(birthYear) : null
      );
      toast.success("Kayıt başarılı 🎉 Şimdi giriş yapabilirsiniz.");

      // 🔁 Üst bileşene haber ver (sekme login'e geçsin)
      onSuccess?.();

      // 🔒 URL'i de güncelle (yeniden girişte login sekmesiyle gelsin)
      navigate("/login?tab=login", { replace: true });
    } catch (e: any) {
      const d = e?.response?.data;
      toast.error(
        d?.detail === "email_in_use"
          ? "Bu e-posta zaten kayıtlı"
          : typeof d?.detail === "string"
          ? d.detail
          : "Kayıt başarısız"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <label className="text-sm text-muted-foreground">E-posta</label>
        <Input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Parola</label>
        <Input
          type="password"
          placeholder="En az 8 karakter"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
        />
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Ülke (opsiyonel)</label>
        <Select value={country ?? ""} onValueChange={setCountry}>
          <SelectTrigger>
            <SelectValue placeholder="Ülke seçiniz" />
          </SelectTrigger>
          <SelectContent className="bg-card text-foreground max-h-60 overflow-y-auto">
            {countryOptions.map((c) => (
              <SelectItem key={c.value} value={c.value}>
                <span className="flex items-center gap-2">
                  <span>{c.emoji}</span>
                  <span>{c.label}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Doğum Yılı</label>
        <Select value={birthYear} onValueChange={setBirthYear}>
          <SelectTrigger>
            <SelectValue placeholder="Seçiniz" />
          </SelectTrigger>
          <SelectContent className="bg-card text-foreground max-h-60 overflow-y-auto">
            {years.map((y) => (
              <SelectItem key={y} value={String(y)}>
                {y}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button className="w-full mt-2" onClick={submit} disabled={loading}>
        {loading ? "Kaydediliyor..." : "Kayıt Ol"}
      </Button>
    </div>
  );
}
