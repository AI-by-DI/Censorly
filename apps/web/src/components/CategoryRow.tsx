// src/components/CategoryRow.tsx
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./ui/button";
import MovieCard from "./MovieCard";
import { useEffect, useRef, useState } from "react";

export interface Movie {
  id: string | number;
  title: string;
  image: string;
  warnings?: string[];
}

interface CategoryRowProps {
  title: string;
  movies: Movie[];
  onPlay?: (movie: Movie) => void;
  /** Index’ten geliyor: sansür modu açık mı? */
  censorEnabled?: boolean;
}

const CategoryRow = ({ title, movies, onPlay, censorEnabled }: CategoryRowProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft]   = useState(false);
  const [canRight, setCanRight] = useState(true);

  const recalcArrows = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 0);
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  };

  const scroll = (direction: "left" | "right") => {
    const el = scrollRef.current;
    if (!el) return;
    const amount = Math.max(320, Math.floor(el.clientWidth * 0.9));
    el.scrollBy({ left: direction === "left" ? -amount : amount, behavior: "smooth" });
  };

  // yatay tekerlek kaydırmayı destekle
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        el.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    };
    const onScroll = () => recalcArrows();
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("scroll", onScroll);
    window.addEventListener("resize", recalcArrows);
    recalcArrows();
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", recalcArrows);
    };
  }, []);

  // klavye ok tuşları
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft")  scroll("left");
      if (e.key === "ArrowRight") scroll("right");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="mb-12">
      <h2 className="text-2xl font-semibold mb-4 px-8">{title}</h2>

      <div className="relative group">
        {/* Sol ok */}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => scroll("left")}
          aria-label="Scroll left"
          disabled={!canLeft}
          className={[
            "absolute left-0 top-1/2 -translate-y-1/2 z-10",
            "rounded-full bg-black/50 hover:bg-black/70",
            "opacity-0 group-hover:opacity-100 transition-opacity",
            !canLeft && "opacity-0 pointer-events-none",
          ].join(" ")}
        >
          <ChevronLeft className="w-8 h-8" />
        </Button>

        {/* Kaydırılabilir liste */}
        <div
          ref={scrollRef}
          className="flex gap-4 overflow-x-auto px-8 scroll-smooth scrollbar-hide"
        >
          {movies.map((movie) => {
            const idStr = String(movie.id);
            return (
              <div key={idStr} className="flex-shrink-0 w-48">
                <MovieCard
                  id={idStr}
                  title={movie.title}
                  image={movie.image}
                  warnings={movie.warnings}
                  censorEnabled={!!censorEnabled}
                  onPlay={() => onPlay?.(movie)}
                />
              </div>
            );
          })}
        </div>

        {/* Sağ ok */}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => scroll("right")}
          aria-label="Scroll right"
          disabled={!canRight}
          className={[
            "absolute right-0 top-1/2 -translate-y-1/2 z-10",
            "rounded-full bg-black/50 hover:bg-black/70",
            "opacity-0 group-hover:opacity-100 transition-opacity",
            !canRight && "opacity-0 pointer-events-none",
          ].join(" ")}
        >
          <ChevronRight className="w-8 h-8" />
        </Button>
      </div>
    </div>
  );
};

export default CategoryRow;
