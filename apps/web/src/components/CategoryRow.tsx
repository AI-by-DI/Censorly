import { ChevronLeft, ChevronRight, Play } from "lucide-react";
import { Button } from "./ui/button";
import MovieCard from "./MovieCard";
import { useRef } from "react";

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
}

const CategoryRow = ({ title, movies, onPlay }: CategoryRowProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  const scroll = (direction: "left" | "right") => {
    if (scrollRef.current) {
      const scrollAmount = direction === "left" ? -800 : 800;
      scrollRef.current.scrollBy({ left: scrollAmount, behavior: "smooth" });
    }
  };

  return (
    <div className="mb-12">
      <h2 className="text-2xl font-semibold mb-4 px-8">{title}</h2>
      <div className="relative group">
        <Button
          variant="ghost"
          size="icon"
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-black/50 hover:bg-black/70 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={() => scroll("left")}
        >
          <ChevronLeft className="w-8 h-8" />
        </Button>

        <div ref={scrollRef} className="flex gap-4 overflow-x-auto scrollbar-hide px-8 scroll-smooth">
          {movies.map((movie) => {
            const idStr = String(movie.id);
            return (
              <div key={idStr} className="flex-shrink-0 w-48 relative group/item">
                <MovieCard
                  id={idStr}
                  title={movie.title}
                  image={movie.image}
                  warnings={movie.warnings}
                />
                <Button
                  size="icon"
                  className="absolute inset-x-0 bottom-3 mx-auto opacity-0 group-hover/item:opacity-100 transition-opacity bg-primary hover:bg-primary/80"
                  onClick={() => onPlay?.(movie)}
                >
                  <Play className="w-5 h-5" />
                </Button>
              </div>
            );
          })}
        </div>

        <Button
          variant="ghost"
          size="icon"
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-black/50 hover:bg-black/70 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={() => scroll("right")}
        >
          <ChevronRight className="w-8 h-8" />
        </Button>
      </div>
    </div>
  );
};

export default CategoryRow;
