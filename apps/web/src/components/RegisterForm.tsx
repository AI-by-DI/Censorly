// src/components/RegisterForm.tsx
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

  const years = useMemo(() => {
    const now = new Date().getFullYear();
    return Array.from({ length: 101 }, (_, i) => now - i).filter((y) => y >= now - 100);
  }, []);

  const validate = useCallback((): string | null => {
    if (!email.trim()) return "Email is required";
    if (!emailRe.test(email.trim())) return "Enter a valid email address";
    if (pw.length < 8) return "Password must be at least 8 characters";
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
      toast.success("Sign-up successful 🎉 You can sign in now.");

      // Tell parent (so the tab switches to login)
      onSuccess?.();

      // And make sure URL opens the login tab if user revisits
      navigate("/login?tab=login", { replace: true });
    } catch (e: any) {
      const d = e?.response?.data;
      toast.error(
        d?.detail === "email_in_use"
          ? "This email is already registered"
          : typeof d?.detail === "string"
          ? d.detail
          : "Sign-up failed"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <label className="text-sm text-muted-foreground">Email</label>
        <Input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Password</label>
        <Input
          type="password"
          placeholder="At least 8 characters"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
        />
      </div>

      <div>
        <label className="text-sm text-muted-foreground">Country (optional)</label>
        <Select value={country ?? ""} onValueChange={setCountry}>
          <SelectTrigger>
            <SelectValue placeholder="Select a country" />
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
        <label className="text-sm text-muted-foreground">Birth Year</label>
        <Select value={birthYear} onValueChange={setBirthYear}>
          <SelectTrigger>
            <SelectValue placeholder="Select" />
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
        {loading ? "Creating account…" : "Sign Up"}
      </Button>
    </div>
  );
}
