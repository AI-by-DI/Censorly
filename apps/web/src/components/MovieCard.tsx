import { Play } from "lucide-react";
import { Button } from "./ui/button";

type Props = {
  id: string;
  title: string;
  image: string;
  warnings?: string[];
  censorEnabled?: boolean;
  onPlay?: () => void;
};

export default function MovieCard({
  title,
  image,
  warnings = [],
  censorEnabled = false,
  onPlay,
}: Props) {
  const ctaText = censorEnabled ? "Watch with Filters" : "Watch Now";

  return (
    <div className="relative rounded-xl overflow-hidden bg-muted/20">
      <img
        src={image}
        alt={title}
        className="w-full h-72 object-cover"
        loading="lazy"
      />

      <div className="absolute inset-x-0 bottom-0 p-3 flex flex-col gap-2
                      bg-gradient-to-t from-black/70 via-black/40 to-transparent">
        <h3 className="text-white font-semibold drop-shadow">{title}</h3>

        <div className="flex items-center gap-1 flex-wrap">
          {warnings.map((w) => (
            <span
              key={w}
              className="px-2 py-0.5 rounded-full text-[10px] bg-white/10 text-white/80 border border-white/20"
            >
              {w}
            </span>
          ))}
        </div>

        {/* ← BUTON: metin sansür moduna göre değişiyor ve artık “Play” sabit değil */}
        <Button
      onClick={onPlay}
className={
  censorEnabled
    ? "bg-green-400 hover:bg-green-300 text-black font-medium shadow-md shadow-green-900/20 transition-all"
    : "bg-primary hover:bg-primary/90 text-primary-foreground"
}

      aria-label={ctaText}
    >
      <Play className="w-4 h-4 mr-2" />
      {ctaText}
    </Button>

      </div>
    </div>
  );
}
