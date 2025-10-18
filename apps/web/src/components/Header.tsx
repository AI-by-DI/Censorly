import { useEffect, useState } from "react";
import { SlidersHorizontal, Eye, EyeOff, LogOut, Menu, X, Search as SearchIcon } from "lucide-react";
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

  // Mobile menu state
  const [open, setOpen] = useState(false);
  const closeMenu = () => setOpen(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-b from-background/90 to-transparent backdrop-blur supports-[backdrop-filter]:backdrop-blur px-4 md:px-8 py-3">
      <div className="mx-auto w-full max-w-7xl flex items-center justify-between gap-3">
        {/* Sol: Logo + (Mobile) Menu button */}
        <div className="flex items-center gap-2">
          {/* Mobile: Hamburger */}
          <button
            className="md:hidden inline-flex h-10 w-10 items-center justify-center rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition"
            onClick={() => setOpen((s) => !s)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="mobile-menu"
          >
            {open ? <X className="h-5 w-5 text-white" /> : <Menu className="h-5 w-5 text-white" />}
          </button>

          {/* Logo */}
          <button
            onClick={() => { closeMenu(); navigate("/index"); }}
            className="text-2xl md:text-3xl font-extrabold tracking-tight text-white drop-shadow-sm select-none"
            aria-label="Go home"
          >
            Censorly
          </button>
        </div>

        {/* Orta: Arama (md ve üstü görünür) */}
        <div className="hidden md:block w-full max-w-xl">
          <SearchBox />
        </div>

        {/* Sağ taraf */}
        <div className="flex items-center gap-2">
          {/* md+: Censor toggle metinli, sm: ikon+etiket */}
          <Button
            variant={enabled ? "default" : "outline"}
            className={cn(
              "flex items-center gap-2 rounded-full px-3 md:px-4 py-2 transition-all text-sm font-medium shadow-md",
              enabled
                ? "bg-green-400 hover:bg-green-300 text-black shadow-green-900/20"
                : "bg-transparent border border-border text-muted-foreground hover:bg-muted/40"
            )}
            onClick={toggle}
            title={enabled ? "Censor Mode is ON" : "Censor Mode is OFF"}
          >
            {enabled ? (
              <>
                <Eye className="w-4 h-4 text-black/80" />
                <span className="hidden sm:inline font-semibold">Censor:</span>
                <span className="font-semibold">{/* always visible */}ON</span>
              </>
            ) : (
              <>
                <EyeOff className="w-4 h-4 text-muted-foreground" />
                <span className="hidden sm:inline font-semibold">Censor:</span>
                <span className="font-semibold text-red-400">OFF</span>
              </>
            )}
          </Button>

          {/* md+: Preferences & Logout butonları */}
          <div className="hidden md:flex items-center gap-2">
            <div className="relative">
              <Link to="/profile" aria-label="Open preferences">
                <Button
                  variant="secondary"
                  className="rounded-full px-4 py-2 bg-white/10 hover:bg-white/15 border border-white/20 text-white flex items-center gap-2"
                  title="Set your content filters and preferences"
                >
                  <SlidersHorizontal className="w-4 h-4" />
                  <span className="hidden lg:inline font-medium">Preferences</span>
                  <span className="lg:hidden font-medium">Prefs</span>
                </Button>
              </Link>

              {showPrefsNudge && (
                <span
                  className="absolute -right-2 -top-2 select-none rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-semibold text-white shadow-lg animate-bounce"
                  role="status"
                >
                  Set filters
                </span>
              )}
            </div>

            <Button
              onClick={handleLogout}
              variant="ghost"
              className="h-9 px-3 text-white/80 hover:text-white hover:bg-white/10 gap-2"
              title="Log out"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden lg:inline">Log out</span>
            </Button>
          </div>

          {/* sm: Quick search button (mobile) */}
          <button
            onClick={() => navigate("/index#search")}
            className="md:hidden inline-flex h-10 w-10 items-center justify-center rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition"
            aria-label="Search"
            title="Search"
          >
            <SearchIcon className="h-5 w-5 text-white" />
          </button>
        </div>
      </div>

      {/* Mobile slide-down menu */}
      <div
        id="mobile-menu"
        className={cn(
          "md:hidden absolute left-0 right-0 mt-3 px-4 transition-[max-height,opacity] duration-300 ease-out overflow-hidden",
          open ? "max-h-[420px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="mx-4 rounded-2xl border border-white/10 bg-black/70 backdrop-blur p-4 shadow-2xl">
          {/* Arama kutusu mobilde panel içinde */}
          <div className="mb-3">
            <SearchBox />
          </div>

          <div className="grid gap-2">
            <Link to="/profile" onClick={closeMenu}>
              <Button
                variant="secondary"
                className="w-full justify-start rounded-xl bg-white/10 hover:bg-white/15 border border-white/20 text-white gap-2"
              >
                <SlidersHorizontal className="w-4 h-4" />
                Preferences
              </Button>
            </Link>

            <Button
              onClick={() => { closeMenu(); handleLogout(); }}
              variant="ghost"
              className="w-full justify-start rounded-xl text-white/90 hover:text-white hover:bg-white/10 gap-2"
            >
              <LogOut className="w-4 h-4" />
              Log out
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
