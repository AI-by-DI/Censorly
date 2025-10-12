import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import {
  Play,
  Pause,
  Volume2,
  Maximize,
  SkipForward,
  Eye,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Slider } from "../components/ui/slider";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Textarea } from "../components/ui/textarea";
import Header from "../components/Header";
import { toast } from "sonner";


const API_BASE = import.meta.env.VITE_API_BASE;


interface AnalysisEvent {
  start: number; // ms
  end: number;   // ms
  category: string;
  confidence: number;
}

const Player = () => {
  const { id } = useParams<{ id: string }>();
  const videoRef = useRef<HTMLVideoElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisEvent[]>([]);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);

  // 🎯 backend’ten video ve analiz sonuçlarını getir
  useEffect(() => {
    const fetchData = async () => {
      try {
        toast.info("Loading video and analysis...");
        const res = await fetch(`${API_BASE}/api/analyze/${id}`);
        const analyzeData = await res.json();
        setAnalysis(analyzeData.results || analyzeData); // flexible structure

        // redact edilmiş video varsa çek
        const vidRes = await fetch(`${API_BASE}/api/redact/${id}`);
        if (!vidRes.ok) throw new Error("Video fetch failed");
        const blob = await vidRes.blob();
        const url = URL.createObjectURL(blob);
        setVideoUrl(url);
        setLoading(false);
        toast.success("Video ready!");
      } catch (err) {
        console.error(err);
        toast.error("Could not load video");
        setLoading(false);
      }
    };

    fetchData();
  }, [id]);

  // ⏱ video oynarken zaman değişimini takip et
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const handleTimeUpdate = () => {
      const timeMs = video.currentTime * 1000;
      setCurrentTime(timeMs);
      // aktif sahnede hassas içerik varsa uyarı ver
      const activeEvent = analysis.find(
        (a) => timeMs >= a.start && timeMs <= a.end
      );
      if (activeEvent) {
        setShowWarning(true);
      }
    };
    video.addEventListener("timeupdate", handleTimeUpdate);
    return () => video.removeEventListener("timeupdate", handleTimeUpdate);
  }, [analysis]);

  // 🧠 kullanıcı blur / skip / normal kararını verir
  const handleAction = async (action: string) => {
    setShowWarning(false);
    toast.success(`Content ${action}`, {
      description: "Continuing playback with your preference",
    });

    try {
      await fetch(`${API_BASE}/api/feedback/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: id, action }),
      });
    } catch (e) {
      console.warn("feedback not saved");
    }
  };

  // 👍👎 geri bildirim
  const handleFeedback = async (positive: boolean) => {
    if (positive) {
      toast.success("Thanks for your feedback!");
      setShowFeedback(false);
    } else {
      setShowFeedback(true);
    }
  };

  const submitFeedback = async () => {
    try {
      await fetch(`${API_BASE}/api/feedback/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: id, text: feedback }),
      });
      toast.success("Feedback submitted. Thank you!");
      setFeedback("");
      setShowFeedback(false);
    } catch {
      toast.error("Failed to send feedback");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center text-muted-foreground text-xl">
        Loading video...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black">
      <Header />

      {/* 🎬 video alanı */}
      <div className="relative w-full h-screen flex items-center justify-center">
        <video
          ref={videoRef}
          src={videoUrl ?? ""}
          className="w-full h-full object-contain"
          controls={false}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />

        {/* timeline (analiz işaretçileriyle) */}
        <div className="absolute bottom-24 left-8 right-8 z-10">
          <div className="relative h-2 bg-secondary rounded-full overflow-hidden">
            <div
              className="absolute h-full bg-primary transition-all duration-200"
              style={{
                width: `${
                  videoRef.current
                    ? (videoRef.current.currentTime /
                        videoRef.current.duration) *
                      100
                    : 0
                }%`,
              }}
            />
            {analysis.map((a, i) => (
              <div
                key={i}
                className="absolute h-4 w-1 top-1/2 -translate-y-1/2 rounded-sm"
                style={{
                  backgroundColor:
                    a.category === "blood"
                      ? "#ef4444"
                      : a.category === "violence"
                      ? "#eab308"
                      : "#8b5cf6",
                  left: `${(a.start / (videoRef.current?.duration! * 1000)) * 100}%`,
                }}
              />
            ))}
          </div>
        </div>

        {/* 🎛️ kontroller */}
        <div className="absolute bottom-8 left-8 right-8 z-10">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                size="icon"
                variant="ghost"
                onClick={() => {
                  const video = videoRef.current;
                  if (!video) return;
                  if (video.paused) video.play();
                  else video.pause();
                }}
                className="w-12 h-12"
              >
                {isPlaying ? (
                  <Pause className="w-6 h-6" />
                ) : (
                  <Play className="w-6 h-6" />
                )}
              </Button>
              <div className="flex items-center gap-2">
                <Volume2 className="w-5 h-5" />
                <Slider defaultValue={[70]} max={100} className="w-24" />
              </div>
              <span className="text-sm text-muted-foreground">
                {Math.floor(currentTime / 60000)}:
                {String(Math.floor((currentTime % 60000) / 1000)).padStart(
                  2,
                  "0"
                )}
              </span>
            </div>
            <Button size="icon" variant="ghost">
              <Maximize className="w-5 h-5" />
            </Button>
          </div>
        </div>

        {/* ⚠️ içerik uyarısı */}
        <Dialog open={showWarning} onOpenChange={setShowWarning}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-violence/20 flex items-center justify-center">
                  <Eye className="w-5 h-5 text-violence" />
                </div>
                Sensitive Scene Detected
              </DialogTitle>
              <DialogDescription>
                Violence or disturbing content ahead. What would you like to do?
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-3 mt-4">
              <Button
                onClick={() => handleAction("blur")}
                variant="default"
                className="w-full"
              >
                Blur Scene
              </Button>
              <Button
                onClick={() => handleAction("skip")}
                variant="secondary"
                className="w-full"
              >
                <SkipForward className="w-4 h-4 mr-2" />
                Skip Scene
              </Button>
              <Button
                onClick={() => handleAction("continue")}
                variant="outline"
                className="w-full"
              >
                Continue Normally
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* 🧾 feedback form */}
        <Dialog open={showFeedback} onOpenChange={setShowFeedback}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Filtering Feedback</DialogTitle>
              <DialogDescription>
                Help us improve by describing what went wrong.
              </DialogDescription>
            </DialogHeader>
            <Textarea
              placeholder="Describe the issue..."
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              className="min-h-24"
            />
            <div className="flex gap-3">
              <Button onClick={submitFeedback} className="flex-1">
                Submit Feedback
              </Button>
              <Button variant="outline" onClick={() => setShowFeedback(false)}>
                Cancel
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* 👍👎 mini feedback prompt */}
      {!showWarning && !loading && (
        <div className="fixed bottom-8 right-8 z-50 p-6 bg-card border border-border rounded-xl shadow-xl animate-slide-up max-w-sm">
          <h3 className="font-semibold mb-2">
            Did the filtering work correctly?
          </h3>
          <div className="flex gap-3">
            <Button
              onClick={() => handleFeedback(true)}
              variant="default"
              className="flex-1"
            >
              <ThumbsUp className="w-4 h-4 mr-2" />
              Yes
            </Button>
            <Button
              onClick={() => handleFeedback(false)}
              variant="outline"
              className="flex-1"
            >
              <ThumbsDown className="w-4 h-4 mr-2" />
              No
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Player;
