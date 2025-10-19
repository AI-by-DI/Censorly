import { useState, useMemo, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card, CardContent } from "../components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import RegisterForm from "../components/RegisterForm";
import { authApi } from "../lib/api";

type TabKey = "login" | "register";

export default function LoginPage() {
  const nav = useNavigate();
  const location = useLocation();

  const initialTab = useMemo<TabKey>(() => {
    const params = new URLSearchParams(location.search);
    return params.get("tab") === "register" ? "register" : "login";
  }, [location.search]);

  const [tab, setTab] = useState<TabKey>(initialTab);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const next = params.get("tab") === "register" ? "register" : "login";
    setTab(next);
  }, [location.search]);

  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [loading, setLoading] = useState(false);

  const onLogin = async () => {
    if (!email.trim() || !pw) return toast.error("Email and password are required");
    try {
      setLoading(true);
      await authApi.login(email.trim(), pw);
      toast.success("Signed in successfully 🎉");
      nav("/index", { replace: true });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Sign-in failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-[100svh] w-full overflow-hidden text-white">
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        style={{ backgroundImage: "url('/landing.jpg')" }}
      />
      <div className="absolute inset-0 bg-black/50" />

      <div className="relative z-40 min-h-[100svh] flex items-center justify-center px-4 py-10">
        <Card className="w-full max-w-md bg-card/90 backdrop-blur-sm border border-white/10 rounded-2xl shadow-xl">
          <CardContent className="p-8">
            <h2 className="text-3xl font-bold text-center mb-6 text-white">Censorly</h2>

            <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)} className="w-full">
              <TabsList className="grid grid-cols-2 w-full mb-6">
                <TabsTrigger value="login">Sign In</TabsTrigger>
                <TabsTrigger value="register">Sign Up</TabsTrigger>
              </TabsList>

              <TabsContent value="login">
                <div className="space-y-4">
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
                      placeholder="••••••••"
                      value={pw}
                      onChange={(e) => setPw(e.target.value)}
                    />
                  </div>

                  <Button className="w-full mt-2" onClick={onLogin} disabled={loading}>
                    {loading ? "Signing in..." : "Sign In"}
                  </Button>

                  {/* Forgot password */}
                  <p className="mt-3 text-center text-sm text-white/70">
                    Forgot your password?{" "}
                    <Link to="/forgot-password" className="text-red-400 hover:text-red-300 underline">
                      Reset it
                    </Link>
                  </p>
                </div>

                <p className="mt-4 text-center text-sm text-white/70">
                  Don’t have an account?{" "}
                  <Link to="/login?tab=register" className="text-red-400 hover:text-red-300 underline">
                    Sign up
                  </Link>
                </p>
              </TabsContent>

              <TabsContent value="register">
                <RegisterForm onSuccess={() => setTab("login")} />
                <p className="mt-4 text-center text-sm text-white/70">
                  Already have an account?{" "}
                  <Link to="/login?tab=login" className="text-red-400 hover:text-red-300 underline">
                    Sign in
                  </Link>
                </p>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
