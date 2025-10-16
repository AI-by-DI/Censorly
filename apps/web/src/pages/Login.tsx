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
    if (!email.trim() || !pw) return toast.error("E-posta ve parola gerekli");
    try {
      setLoading(true);
      await authApi.login(email.trim(), pw);
      toast.success("Giriş başarılı 🎉");
      nav("/index", { replace: true });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Giriş başarısız");
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
                <TabsTrigger value="login">Giriş Yap</TabsTrigger>
                <TabsTrigger value="register">Kayıt Ol</TabsTrigger>
              </TabsList>

              <TabsContent value="login">
                <div className="space-y-4">
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
                      placeholder="••••••••"
                      value={pw}
                      onChange={(e) => setPw(e.target.value)}
                    />
                  </div>

                  <Button className="w-full mt-2" onClick={onLogin} disabled={loading}>
                    {loading ? "Giriş yapılıyor..." : "Giriş Yap"}
                  </Button>

                  {/* Şifremi unuttum */}
                  <p className="mt-3 text-center text-sm text-white/70">
                    Parolanı mı unuttun?{" "}
                    <Link to="/forgot-password" className="text-red-400 hover:text-red-300 underline">
                      Sıfırla
                    </Link>
                  </p>
                </div>

                <p className="mt-4 text-center text-sm text-white/70">
                  Hesabın yok mu?{" "}
                  <Link to="/login?tab=register" className="text-red-400 hover:text-red-300 underline">
                    Kayıt ol
                  </Link>
                </p>
              </TabsContent>

              <TabsContent value="register">
                <RegisterForm onSuccess={() => setTab("login")} />
                <p className="mt-4 text-center text-sm text-white/70">
                  Zaten hesabın var mı?{" "}
                  <Link to="/login?tab=login" className="text-red-400 hover:text-red-300 underline">
                    Giriş yap
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
