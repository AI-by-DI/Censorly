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
  const [lastError, setLastError] = useState<string | null>(null); // show last error on screen
  const nav = useNavigate();

  const onSubmit = async () => {
    setLastError(null);

    if (!email.trim() || !newPw.trim()) {
      toast.error("Email and new password are required");
      setLastError("missing_fields");
      return;
    }

    try {
      setLoading(true);
      // Backend expects a Form(...) — send FormData
      const fd = new FormData();
      fd.append("email", email.trim());
      fd.append("new_password", newPw);

      const API_BASE = import.meta.env.VITE_API_URL; // read from env
      const res = await axios.post(`${API_BASE}/auth/reset-password`, fd, {
        headers: {},            // Content-Type will be set automatically for FormData
        validateStatus: () => true, // let us handle non-2xx manually
      });

      if (res.status === 200 && res.data?.detail === "password_reset_success") {
        toast.success("Password updated successfully 🎉");
        nav("/login?tab=login", { replace: true });
        return;
      }

      const msg = res.data?.detail || `HTTP ${res.status}`;
      setLastError(String(msg));
      toast.error(String(msg));
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "request_failed";
      setLastError(String(msg));
      toast.error(String(msg));
    } finally {
      setLoading(false);
    }
  };

  // Submit with Enter
  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !loading) onSubmit();
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-card/90 p-8 rounded-2xl shadow-lg text-white">
        <h2 className="text-2xl font-bold mb-4 text-center">Reset Your Password</h2>

        <label className="text-sm text-muted-foreground">Email address</label>
        <Input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label="email"
        />

        <label className="text-sm text-muted-foreground mt-4 block">New password</label>
        <Input
          type="password"
          placeholder="••••••••"
          value={newPw}
          onChange={(e) => setNewPw(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label="new password"
        />

        <Button
          type="button"
          className="w-full mt-5"
          onClick={onSubmit}
          disabled={loading}
          aria-busy={loading}
          aria-label="submit new password"
        >
          {loading ? "Updating..." : "Update Password"}
        </Button>

        {/* Debug panel: show last error (optional) */}
        {lastError && (
          <div className="mt-4 text-xs text-red-300 break-words">
            Debug: {lastError}
          </div>
        )}
      </div>
    </div>
  );
}
