// src/components/Header.tsx
import { User, Eye, EyeOff } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "./ui/button";
import { useCensorStore } from "../store/censorStore";
import { cn } from "../lib/utils";
import SearchBox from "../components/SearchBox";

const Header = () => {
  const navigate = useNavigate();
  const { enabled, toggle } = useCensorStore();

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-b from-background to-transparent px-8 py-4">
      <div className="container mx-auto flex items-center justify-between">
        {/* Logo */}
        <button
          onClick={() => navigate("/")}
          className="text-3xl font-bold text-primary select-none"
          aria-label="Go home"
        >
          Censorly
        </button>

        {/* Orta kısım: Arama kutusu */}
        <div className="hidden md:block w-full max-w-xl">
          <SearchBox />
        </div>

        {/* Sağ kısım */}
        <div className="flex items-center gap-4">
          {/* Sansür modu */}
          <Button
            variant={enabled ? "default" : "outline"}
            className={cn(
              "flex items-center gap-2 rounded-full px-4 py-2 transition-all text-sm font-medium shadow-md",
              enabled
                ? "bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-black shadow-md shadow-amber-900/30"
                : "bg-transparent border border-border text-muted-foreground hover:bg-muted/40"
            )}
            onClick={toggle}
            title={enabled ? "Censor Mode is ON" : "Censor Mode is OFF"}
          >
            {enabled ? (
              <>
                <Eye className="w-4 h-4 text-black/80" />
                <span className="font-semibold">Censor Mode: </span>
                <span className="font-semibold text-black">ON</span>
              </>
            ) : (
              <>
                <EyeOff className="w-4 h-4 text-muted-foreground" />
                <span className="font-semibold">Censor Mode: </span>
                <span className="font-semibold text-red-400">OFF</span>
              </>
            )}
          </Button>

          {/* Profil */}
          <Link to="/profile" aria-label="Profile">
            <Button variant="ghost" size="icon">
              <User className="w-5 h-5" />
            </Button>
          </Link>
        </div>
      </div>
    </header>
  );
};

export default Header;
