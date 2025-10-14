import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Play, Pause, Volume2, Maximize, SkipForward, Eye,
  ThumbsUp, ThumbsDown
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Slider } from "../components/ui/slider";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Textarea } from "../components/ui/textarea";
import Header from "../components/Header";
import { toast } from "sonner";

const API_BASE = import.meta.env.VITE_API_BASE as string;

type AnalysisEvent = { start: number; end: number; category: string; confidence: number };

function getAuthHeaders(): HeadersInit {
  // Eğer auth yoksa "" bırakın. Varsa burayı kendi token okumanızla değiştirin.
  const token = ""; // e.g., localStorage.getItem("access_token") || ""
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function Player() {
  const { id = "" } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const startFiltered = useMemo(() => search.get("mode") === "censored", [search]);

  const videoRef = useRef<HTMLVideoElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisEvent[]>([]);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [censorMode, setCensorMode] = useState(startFiltered);
  const [volume, setVolume] = useState(0.7);

  const headers = getAuthHeaders();

  // video url yükle
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        toast.info("Loading video...");

        const url = censorMode
          ? await (async () => {
              const r = await fetch(
                `${API_BASE}/redactions/download/${id}?profile_id=active&presigned=true`,
                { headers }
              );
              if (!r.ok) throw new Error("redactions failed");
              const j = await r.json();
              if (!j?.redacted?.url) throw new Error("no redacted url");
              return j.redacted.url as string;
            })()
          : await (async () => {
              const r = await fetch(`${API_BASE}/videos/${id}/stream`, { headers });
              if (!r.ok) throw new Error("stream failed");
              const { url } = await r.json();
              if (!url) throw new Error("no stream url");
              return url as string;
            })();

        if (!cancelled) {
          setVideoUrl(url);
          setLoading(false);
          toast.success("Video ready!");
        }
      } catch (e) {
        console.error(e);
        if (!cancelled) {
          setLoading(false);
          toast.error("Could not load video");
        }
      }
    };
    load();
    return () => { cancelled = true; };
    // `censorMode` değişince doğru sürümü yeniden çeker
  }, [API_BASE, id, censorMode]);

  // timeline: current time takibi + (opsiyonel) uyarı
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.volume = volume;

    const onTime = () => {
      const t = v.currentTime * 1000;
      setCurrentTime(t);
      if (!censorMode) return;
      const ev = analysis.find(a => t >= a.start && t <= a.end);
      if (ev) setShowWarning(true);
    };
    v.addEventListener("timeupdate", onTime);
    return () => v.removeEventListener("timeupdate", onTime);
  }, [analysis, censorMode, volume]);

  const toggleCensorMode = async () => {
    setCensorMode((prev) => !prev);
    // URL fetch’i useEffect’te yapılacak
  };

  const handleAction = (action: "skip" | "blur" | "continue") => {
    setShowWarning(false);
    const v = videoRef.current;
    if (!v) return;
    if (action === "skip") {
      const now = currentTime;
      const nextEvent = analysis.find(a => a.start > now);
      v.currentTime = nextEvent ? nextEvent.start / 1000 : v.currentTime + 2;
      toast.success("Scene skipped!");
    } else if (action === "blur") {
      // Blur efekti gerçek zamanlı uygulanmıyor; bu demoyu bilgi amaçlı tutuyoruz.
      toast.success("Scene blurred (demo)");
    } else {
      toast.info("Continuing normally");
    }
  };

  const handleFeedback = (positive: boolean) => {
    if (positive) {
      toast.success("Thanks for your feedback!");
      setShowFeedback(false);
    } else {
      setShowFeedback(true);
    }
  };

  const submitFeedback = async () => {
    try {
      await fetch(`${API_BASE}/feedback/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ video_id: id, text: feedback }),
      });
      toast.success("Feedback submitted. Thank you!");
      setFeedback(""); setShowFeedback(false);
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

      {/* video kanvası */}
      <div className="relative w-full h-[calc(100vh-64px)]">
        <video
          key={videoUrl}                   // URL değişince tam yenile
          ref={videoRef}
          src={videoUrl}
          className="absolute inset-0 w-full h-full object-contain"
          controls={false}
          playsInline
          controlsList="nodownload noplaybackrate nofullscreen"
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />

        {/* alt timeline (opsiyonel) */}
        <div className="pointer-events-none absolute bottom-24 left-8 right-8 z-10">
          <div className="relative h-2 bg-secondary rounded-full overflow-hidden">
            <div
              className="absolute h-full bg-primary transition-all duration-200"
              style={{
                width: `${
                  videoRef.current
                    ? (videoRef.current.currentTime / (videoRef.current.duration || 1)) * 100
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
                    a.category === "blood" ? "#ef4444" :
                    a.category === "violence" ? "#eab308" : "#8b5cf6",
                  left: `${
                    videoRef.current?.duration
                      ? (a.start / (videoRef.current.duration * 1000)) * 100
                      : 0
                  }%`,
                }}
              />
            ))}
          </div>
        </div>

        {/* kontroller */}
        <div className="absolute bottom-8 left-8 right-8 z-20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                size="icon"
                variant="ghost"
                onClick={() => {
                  const v = videoRef.current;
                  if (!v) return;
                  v.paused ? v.play() : v.pause();
                }}
                className="w-12 h-12"
              >
                {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
              </Button>

              <div className="flex items-center gap-2">
                <Volume2 className="w-5 h-5" />
                <Slider
                  value={[Math.round(volume * 100)]}
                  onValueChange={(val) => {
                    const v = videoRef.current;
                    const vol = (val?.[0] ?? 70) / 100;
                    setVolume(vol);
                    if (v) v.volume = vol;
                  }}
                  max={100}
                  className="w-24"
                />
              </div>

              <span className="text-sm text-muted-foreground">
                {Math.floor(currentTime / 60000)}:{String(Math.floor((currentTime % 60000) / 1000)).padStart(2, "0")}
              </span>
            </div>

            <div className="flex items-center gap-3">
              <Button onClick={toggleCensorMode} variant={censorMode ? "default" : "secondary"}>
                {censorMode ? "Filtered Mode: ON" : "Filtered Mode: OFF"}
              </Button>
              <Button size="icon" variant="ghost">
                <Maximize className="w-5 h-5" />
              </Button>
            </div>
          </div>
        </div>

        {/* uyarı */}
        <Dialog open={showWarning} onOpenChange={setShowWarning}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-violence/20 flex items-center justify-center">
                  <Eye className="w-5 h-5 text-violence" />
                </div>
                Sensitive Scene Detected
              </DialogTitle>
              <DialogDescription>Violence or disturbing content ahead. What would you like to do?</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-3 mt-4">
              <Button className="w-full" onClick={() => handleAction("blur")}>Blur Scene</Button>
              <Button className="w-full" variant="secondary" onClick={() => handleAction("skip")}>
                <SkipForward className="w-4 h-4 mr-2" /> Skip Scene
              </Button>
              <Button className="w-full" variant="outline" onClick={() => handleAction("continue")}>
                Continue Normally
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* feedback kartı */}
        {!showWarning && (
          <div className="absolute bottom-8 right-8 z-20 p-6 bg-card border border-border rounded-xl shadow-xl max-w-sm">
            <h3 className="font-semibold mb-2">Did the filtering work correctly?</h3>
            <div className="flex gap-3">
              <Button className="flex-1" onClick={() => handleFeedback(true)}>
                <ThumbsUp className="w-4 h-4 mr-2" /> Yes
              </Button>
              <Button className="flex-1" variant="outline" onClick={() => handleFeedback(false)}>
                <ThumbsDown className="w-4 h-4 mr-2" /> No
              </Button>
            </div>

            {/* olumsuzsa açıklama */}
            <Dialog open={showFeedback} onOpenChange={setShowFeedback}>
              <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle>Tell us what went wrong</DialogTitle>
                  <DialogDescription>We’ll use your feedback to improve the filters.</DialogDescription>
                </DialogHeader>
                <Textarea
                  placeholder="Example: Clown scene was not blurred at 00:35…"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={5}
                />
                <div className="flex justify-end gap-2">
                  <Button variant="secondary" onClick={() => setShowFeedback(false)}>Cancel</Button>
                  <Button onClick={submitFeedback}>Send</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        )}
      </div>
    </div>
  );
}
