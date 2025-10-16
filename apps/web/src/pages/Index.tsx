// src/pages/Index.tsx
import { useEffect, useMemo, useState } from "react";
import { Play } from "lucide-react";
import { Button } from "../components/ui/button";
import Header from "../components/Header";
import Footer from "../components/Footer";
import CategoryRow from "../components/CategoryRow";
import { useNavigate } from "react-router-dom";
import { useCensorStore } from "../store/censorStore";

const API_BASE = import.meta.env.VITE_API_BASE as string;

type MovieCardT = {
  id: string;
  title: string;
  image: string;
  warnings: string[];
};

export default function Index() {
  const navigate = useNavigate();
  const { enabled } = useCensorStore();

  const [items, setItems] = useState<MovieCardT[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let canceled = false;
    (async () => {
      try {
        setLoading(true);
        const r = await fetch(`${API_BASE}/videos?limit=24`);
        const data: Array<{ id: string; title: string; poster_url?: string | null }> = await r.json();

        const placeholders = ["/movie-1.jpg", "/movie-2.jpg", "/movie-3.jpg", "/movie-4.jpg"];
        const mapped: MovieCardT[] = data.map((v, i) => ({
          id: v.id,
          title: v.title || "Untitled",
          image: v.poster_url || placeholders[i % placeholders.length],
          warnings: [],
        }));

        if (!canceled) setItems(mapped);
      } catch {
        if (!canceled) setItems([]);
      } finally {
        if (!canceled) setLoading(false);
      }
    })();
    return () => {
      canceled = true;
    };
  }, []);

  const recommended = useMemo(() => items.slice(0, 6), [items]);
  const trending = useMemo(() => items.slice(6, 12), [items]);
  const newlyAdded = useMemo(() => items.slice(12, 18), [items]);

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

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />

      {/* Hero Section */}
      <section className="relative h-[90vh] mb-8">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/hero-banner.jpg')" }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/60 to-transparent" />
        <div className="relative container mx-auto h-full flex items-center px-8">
          <div className="max-w-2xl space-y-6 animate-fade-in">
            <h1 className="text-6xl font-bold leading-tight">The Reckoning</h1>
            <p className="text-xl text-muted-foreground">
              When darkness falls, only the brave survive. Watch with personalized content filtering.
            </p>

            <div className="flex gap-4">
              <Button
                size="lg"
                onClick={() => handleWatch()}
                className={
                  enabled
                    ? "bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-black font-semibold shadow-md shadow-amber-900/30 transition-all"
                    : "bg-primary hover:bg-primary/90 text-primary-foreground"
                }
              >
                <Play className="w-5 h-5 mr-2" />
                {enabled ? "Watch with Filters" : "Watch Now"}
              </Button>
            </div>

            <div className="flex gap-2 flex-wrap">
              <span className="px-3 py-1 rounded-full text-sm bg-violence/20 text-violence border border-violence/30">
                Contains Violence
              </span>
              <span className="px-3 py-1 rounded-full text-sm bg-blood/20 text-blood border border-blood/30">
                Contains Blood
              </span>
            </div>
          </div>
        </div>
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
