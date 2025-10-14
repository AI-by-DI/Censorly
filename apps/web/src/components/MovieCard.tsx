import { Play, Info } from "lucide-react";
import { Button } from "./ui/button";
import { useNavigate } from "react-router-dom";

export interface MovieCardProps {
  id: string;
  title: string;
  image: string;
  warnings?: string[];
  onPlay?: (id: string) => void;
  onInfo?: (id: string) => void;
}

const MovieCard = ({ id, title, image, warnings = [], onPlay, onInfo }: MovieCardProps) => {
  const navigate = useNavigate();
  const gotoDefault = () => navigate(`/player/${id}`);

  return (
    <div
      className="group relative cursor-pointer rounded-xl overflow-hidden transition-all duration-300 hover:scale-105 hover:z-10"
      onClick={() => (onPlay ? onPlay(id) : gotoDefault())}
    >
      <div className="aspect-[2/3] relative">
        <img src={image} alt={title} className="w-full h-full object-cover" loading="lazy" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
          <div className="absolute bottom-0 left-0 right-0 p-4 translate-y-4 group-hover:translate-y-0 transition-transform duration-300">
            <h3 className="font-semibold text-lg mb-2 line-clamp-2">{title}</h3>

            {warnings.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {warnings.map((w) => (
                  <span key={w} className="px-2 py-0.5 rounded-full text-xs bg-warning text-warning-foreground">
                    {w}
                  </span>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              <Button
                size="sm"
                variant="default"
                className="flex-1"
                onClick={(e) => { e.stopPropagation(); (onPlay ? onPlay(id) : gotoDefault()); }}
              >
                <Play className="w-4 h-4 mr-1" />
                Play
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={(e) => { e.stopPropagation(); onInfo ? onInfo(id) : navigate(`/video/${id}`); }}
                aria-label="More info"
              >
                <Info className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MovieCard;
