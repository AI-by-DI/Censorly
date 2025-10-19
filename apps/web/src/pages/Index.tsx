// src/pages/Index.tsx
import { useEffect, useMemo, useState } from "react";
import { Play, SlidersHorizontal } from "lucide-react";
import { Button } from "../components/ui/button";
import Header from "../components/Header";
import Footer from "../components/Footer";
import CategoryRow from "../components/CategoryRow";
import { useNavigate, Link } from "react-router-dom";
import { useCensorStore } from "../store/censorStore";

const API_BASE = import.meta.env.VITE_API_BASE as string;

type ApiVideo = {
  id: string;
  title: string;
  poster_url?: string | null; // dikey
  hero_url?: string | null;   // yatay
};

type MovieCardT = {
  id: string;
  title: string;
  poster: string | null;
  hero: string | null;
  warnings: string[];
};

export default function Index() {
  const navigate = useNavigate();
  const { enabled } = useCensorStore();

  const [items, setItems] = useState<MovieCardT[]>([]);
  const [loading, setLoading] = useState(true);
  const [heroIdx, setHeroIdx] = useState(0);

  useEffect(() => {
    let canceled = false;
    (async () => {
      try {
        setLoading(true);
        const r = await fetch(`${API_BASE}/videos?limit=24`);
        const data: ApiVideo[] = await r.json();

        const mapped: MovieCardT[] = data.map((v) => ({
          id: v.id,
          title: v.title || "Untitled",
          poster: v.poster_url ?? null,
          hero: v.hero_url ?? null,
          warnings: [],
        }));

        if (!canceled) {
          setItems(mapped);
          setHeroIdx(0);
        }
      } catch {
        if (!canceled) {
          setItems([]);
          setHeroIdx(0);
        }
      } finally {
        if (!canceled) setLoading(false);
      }
    })();
    return () => { canceled = true; };
  }, []);

  // Hero rotator (12s)
  useEffect(() => {
    if (!items.length) return;
    const timer = setInterval(() => {
      setHeroIdx((prev) => (prev + 1) % items.length);
    }, 12000);
    return () => clearInterval(timer);
  }, [items.length]);

  const placeholders = useMemo(() => ["/movie-1.jpg", "/movie-2.jpg", "/movie-3.jpg", "/movie-4.jpg"], []);

  // CategoryRow için poster -> image map
  const toRow = (arr: MovieCardT[], start: number, end: number) =>
    arr.slice(start, end).map((m, i) => ({
      id: m.id,
      title: m.title,
      image: m.poster ?? placeholders[i % placeholders.length],
      warnings: m.warnings,
    }));

  const recommended = useMemo(() => toRow(items, 0, 6), [items, placeholders]);
  const trending    = useMemo(() => toRow(items, 6, 12), [items, placeholders]);
  const newlyAdded  = useMemo(() => toRow(items, 12, 18), [items, placeholders]);

  // Sade “Watch” — index’te bekleme yok, direkt player’a
  const handleWatch = (videoId?: string) => {
    const id = videoId ?? (items[0]?.id || "");
    if (!id) return;
    navigate(enabled ? `/player/${id}?mode=censored` : `/player/${id}?mode=original`);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }

  const hero = items[heroIdx];
  const heroImage = hero?.hero || hero?.poster || "/hero-banner.jpg";

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />

      {/* Hero Section — tıklamaları engellememesi için background katmanlarına pointer-events-none */}
      <section className="relative h-[70svh] md:h-[90vh] mb-6 md:mb-8">
        <div
          className="absolute inset-0 bg-cover bg-center transition-[background-image] duration-700 ease-out pointer-events-none"
          style={{ backgroundImage: `url('${heroImage}')` }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/60 to-transparent pointer-events-none" />
        <div className="relative container mx-auto h-full flex items-center px-4 md:px-8">
          <div className="max-w-2xl space-y-6 animate-fade-in">
            <h1 className="text-3xl sm:text-4xl md:text-6xl font-bold leading-tight">
              {hero?.title ?? "Untitled"}
            </h1>
            <p className="text-base sm:text-lg md:text-xl text-muted-foreground">
              Watch your uploads with personalized content filtering.
            </p>

            <div className="flex flex-wrap gap-3">
              <Button
                size="lg"
                onClick={() => handleWatch(hero?.id)}
                className={`${
                  enabled
                    ? "bg-green-400 hover:bg-green-300 text-black font-medium shadow-md shadow-green-900/20 transition-all"
                    : "bg-primary hover:bg-primary/90 text-primary-foreground"
                } w-full sm:w-auto`}
              >
                <Play className="w-5 h-5 mr-2" />
                {enabled ? "Watch with Filters" : "Watch Now"}
              </Button>

              <Button asChild variant="outline" className="w-full sm:w-auto rounded-full border-white/20 text-white/90 hover:bg-white/10">
                <Link to="/profile">
                  <SlidersHorizontal className="w-4 h-4 mr-2" />
                  Set Preferences
                </Link>
              </Button>
            </div>

            {/* (opsiyonel) statik rozetler */}
            <div className="flex gap-2 flex-wrap pt-1">
              <span className="px-3 py-1 rounded-full text-sm bg-violence/20 text-violence border border-violence/30">
                Contains Violence
              </span>
              <span className="px-3 py-1 rounded-full text-sm bg-blood/20 text-blood border border-blood/30">
                Contains Blood
              </span>
            </div>
          </div>
        </div>

        {items.length > 1 && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
            {items.slice(0, Math.min(items.length, 6)).map((_, i) => (
              <button
                key={i}
                onClick={() => setHeroIdx(i)}
                className={`h-2 w-2 rounded-full ${i === heroIdx ? "bg-white" : "bg-white/40"} hover:bg-white transition`}
                aria-label={`Go to item ${i + 1}`}
              />
            ))}
          </div>
        )}
      </section>

      {/* Content Rows */}
      <main className="flex-1 pb-16">
        <CategoryRow
          title="Recommended for You"
          movies={recommended}
          censorEnabled={enabled}
          onPlay={(m) => handleWatch(String(m.id))}
        />
        <CategoryRow
          title="Trending Now"
          movies={trending}
          censorEnabled={enabled}
          onPlay={(m) => handleWatch(String(m.id))}
        />
        <CategoryRow
          title="Newly Added"
          movies={newlyAdded}
          censorEnabled={enabled}
          onPlay={(m) => handleWatch(String(m.id))}
        />
      </main>

      <Footer />
    </div>
  );
}
