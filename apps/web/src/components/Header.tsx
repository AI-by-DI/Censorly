import { useEffect, useState } from "react";
import { SlidersHorizontal, Eye, EyeOff, LogOut } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "./ui/button";
import { useCensorStore } from "../store/censorStore";
import { cn } from "../lib/utils";
import SearchBox from "../components/SearchBox";

const Header = () => {
  const navigate = useNavigate();
  const { enabled, toggle } = useCensorStore();

  // Tek seferlik “set filters” nudgesi (bu sekme boyunca)
  const [showPrefsNudge, setShowPrefsNudge] = useState<boolean>(() => {
    return !sessionStorage.getItem("prefs_nudged");
  });
  useEffect(() => {
    if (!showPrefsNudge) return;
    const t = setTimeout(() => {
      setShowPrefsNudge(false);
      sessionStorage.setItem("prefs_nudged", "1");
    }, 6000);
    return () => clearTimeout(t);
  }, [showPrefsNudge]);

  const handleLogout = () => {
    try {
      localStorage.removeItem("access");
      window.dispatchEvent(new Event("auth:changed"));
    } finally {
      navigate("/login", { replace: true });
    }
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-b from-background to-transparent px-8 py-4">
      <div className="container mx-auto flex items-center justify-between">
        {/* Logo */}
        <button
          onClick={() => navigate("/index")}
          className="text-3xl font-extrabold tracking-tight text-white drop-shadow-sm select-none"
          aria-label="Go home"
        >
          Censorly
        </button>

        {/* Orta: Arama */}
        <div className="hidden md:block w-full max-w-xl">
          <SearchBox />
        </div>

        {/* Sağ */}
        <div className="flex items-center gap-2">
          {/* Censor mode toggle */}
          <Button
            variant={enabled ? "default" : "outline"}
            className={cn(
              "flex items-center gap-2 rounded-full px-4 py-2 transition-all text-sm font-medium shadow-md",
              enabled
                ?  "bg-green-400 hover:bg-green-300 text-black font-medium shadow-md shadow-green-900/20 transition-all"
                : "bg-transparent border border-border text-muted-foreground hover:bg-muted/40"
              
            )}
            onClick={toggle}
            title={enabled ? "Censor Mode is ON" : "Censor Mode is OFF"}
          >
            {enabled ? (
              <>
                <Eye className="w-4 h-4 text-black/80" />
                <span className="font-semibold">Censor Mode:</span>
                <span className="font-semibold text-black">ON</span>
              </>
            ) : (
              <>
                <EyeOff className="w-4 h-4 text-muted-foreground" />
                <span className="font-semibold">Censor Mode:</span>
                <span className="font-semibold text-red-400">OFF</span>
              </>
            )}
          </Button>

          {/* Preferences — belirgin yönlendirme */}
          <div className="relative">
            <Link to="/profile" aria-label="Open preferences">
              <Button
                variant="secondary"
                className="rounded-full px-4 py-2 bg-white/10 hover:bg-white/15 border border-white/20 text-white flex items-center gap-2"
                title="Set your content filters and preferences"
              >
                <SlidersHorizontal className="w-4 h-4" />
                <span className="hidden sm:inline font-medium">Preferences</span>
              </Button>
            </Link>

            {/* Tek seferlik nudge */}
            {showPrefsNudge && (
              <span
                className="absolute -right-2 -top-2 select-none rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-semibold text-white shadow-lg animate-bounce"
                role="status"
              >
                Set filters
              </span>
            )}
          </div>

          {/* Log out */}
          <Button
            onClick={handleLogout}
            variant="ghost"
            className="h-9 px-3 text-white/80 hover:text-white hover:bg-white/10 gap-2"
            title="Log out"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Log out</span>
          </Button>
        </div>
      </div>
    </header>
  );
};

export default Header;
