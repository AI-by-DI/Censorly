import { useEffect, useState } from "react";
import { Play, Brain, Plus } from "lucide-react";
import { Button } from "../components/ui/button";
import Header from "../components/Header";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

// .env'den backend adresi
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface VideoInfo {
  id: string;
  title: string;
  description: string;
  year: number;
  duration: string;
  genre: string;
  poster_url: string;
  warnings: string[];
  cast?: string;
  director?: string;
}

const VideoDetail = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const [video, setVideo] = useState<VideoInfo | null>(null);
  const [loading, setLoading] = useState(true);

  // 🎯 backend’ten video bilgilerini çek
  useEffect(() => {
    const fetchVideo = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/videos/${id}`);
        if (!res.ok) throw new Error("Video not found");
        const data = await res.json();
        setVideo(data);
      } catch (err) {
        console.error(err);
        toast.error("Video information could not be loaded");
      } finally {
        setLoading(false);
      }
    };
    fetchVideo();
  }, [id]);

  if (loading)
    return (
      <div className="flex items-center justify-center min-h-screen bg-background text-muted-foreground text-lg">
        Loading video details...
      </div>
    );

  if (!video)
    return (
      <div className="flex items-center justify-center min-h-screen bg-background text-destructive text-lg">
        Video not found.
      </div>
    );

  return (
    <div className="min-h-screen bg-background">
      <Header />

      {/* 🎞 Hero Section */}
      <section className="relative h-[70vh] mt-16">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${video.poster_url})` }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/40 to-transparent" />
      </section>

      {/* 📄 Content */}
      <div className="container mx-auto px-8 -mt-32 relative z-10">
        <div className="max-w-4xl space-y-6 animate-slide-up">
          <h1 className="text-5xl font-bold">{video.title}</h1>

          <div className="flex items-center gap-4 text-muted-foreground">
            <span className="text-foreground font-medium">{video.year}</span>
            <span>•</span>
            <span>{video.duration}</span>
            <span>•</span>
            <span>{video.genre}</span>
          </div>

          <p className="text-lg text-muted-foreground leading-relaxed">
            {video.description}
          </p>

          {/* ⚠️ Warnings */}
          <div className="flex gap-2 flex-wrap">
            {video.warnings?.map((w) => (
              <span
                key={w}
                className={`px-3 py-1 rounded-full text-sm border ${
                  w.toLowerCase() === "violence"
                    ? "bg-violence/20 text-violence border-violence/30"
                    : w.toLowerCase() === "blood"
                    ? "bg-blood/20 text-blood border-blood/30"
                    : w.toLowerCase() === "alcohol"
                    ? "bg-alcohol/20 text-alcohol border-alcohol/30"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {w}
              </span>
            ))}
          </div>

          {/* 🎬 Actions */}
          <div className="flex gap-4 pt-4">
            <Button
              size="lg"
              onClick={() => navigate(`/player/${id}`)}
              className="bg-primary hover:bg-primary/90"
            >
              <Play className="w-5 h-5 mr-2" />
              Play Normally
            </Button>
            <Button
              size="lg"
              variant="secondary"
              onClick={() => navigate(`/player/${id}?mode=filter`)}
            >
              <Brain className="w-5 h-5 mr-2" />
              Play with My Filters
            </Button>
            <Button
              size="lg"
              variant="ghost"
              onClick={() => toast.success("Added to your list!")}
            >
              <Plus className="w-5 h-5 mr-2" />
              My List
            </Button>
          </div>

          {/* 🎭 Cast & Crew */}
          <div className="pt-8 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <p className="text-muted-foreground mb-1">Cast</p>
                <p className="text-foreground">
                  {video.cast || "Not available"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground mb-1">Director</p>
                <p className="text-foreground">
                  {video.director || "Unknown"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoDetail;
