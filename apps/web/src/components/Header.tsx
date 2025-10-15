import { Search, User, Eye, EyeOff } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { useCensorStore } from "../store/censorStore";
import { cn } from "../lib/utils"; // shadcn kullanıyorsan genelde var

const Header = () => {
  const { enabled, toggle } = useCensorStore();

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-b from-background to-transparent px-8 py-4">
      <div className="container mx-auto flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="text-3xl font-bold text-primary">
          Censorly
        </Link>

        {/* Sağ kısım */}
        <div className="flex items-center gap-6">
          {/* Arama kutusu */}
          <div className="relative hidden md:block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-5 h-5" />
            <Input
              placeholder="Search movies and series..."
              className="w-80 pl-10 bg-secondary border-border"
            />
          </div>

          {/* Sansür modu butonu (görsel olarak belirgin) */}
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


          {/* Profil butonu */}
          <Link to="/profile">
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
