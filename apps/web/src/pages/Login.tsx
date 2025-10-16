import { useState, useMemo, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { authApi } from "../lib/api";
import RegisterForm from "../components/RegisterForm";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card, CardContent } from "../components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { toast } from "sonner";

type TabKey = "login" | "register";

export default function LoginPage() {
  const nav = useNavigate();
  const location = useLocation();

  const initialTab = useMemo<TabKey>(() => {
    const params = new URLSearchParams(location.search);
    return params.get("tab") === "register" ? "register" : "login";
  }, [location.search]);

  const [tab, setTab] = useState<TabKey>(initialTab);

  // 🔁 URL ?tab= değişirse sekmeyi de güncelle
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const next = params.get("tab") === "register" ? "register" : "login";
    setTab(next);
  }, [location.search]);

  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [loading, setLoading] = useState(false);

  const onLogin = async () => {
    if (!email.trim() || !pw) {
      toast.error("E-posta ve parola gerekli");
      return;
    }
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
    <div className="min-h-screen flex items-center justify-center bg-background text-foreground px-4">
      <Card className="w-full max-w-md bg-card border border-border rounded-2xl shadow-lg animate-fade-in">
        <CardContent className="p-8">
          <h1 className="text-3xl font-bold text-center mb-6">Censorly</h1>

          <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)} className="w-full">
            <TabsList className="grid grid-cols-2 w-full mb-6">
              <TabsTrigger value="login">Giriş Yap</TabsTrigger>
              <TabsTrigger value="register">Kayıt Ol</TabsTrigger>
            </TabsList>

            {/* LOGIN */}
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
              </div>
            </TabsContent>

            {/* REGISTER */}
            <TabsContent value="register">
              <RegisterForm
                // ⬇️ Kayıt başarılı olunca login sekmesine geçir
                onSuccess={() => {
                  setTab("login");
                }}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
