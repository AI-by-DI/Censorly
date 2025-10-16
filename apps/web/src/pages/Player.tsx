// src/pages/Player.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Play, Pause, Volume2, VolumeX, Maximize, SkipForward,
  Eye, ThumbsUp, ThumbsDown, ArrowLeft
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Slider } from "../components/ui/slider";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle
} from "../components/ui/dialog";
import { Textarea } from "../components/ui/textarea";
import { toast } from "sonner";

const API_BASE = import.meta.env.VITE_API_BASE as string;

type AnalysisEvent = { start: number; end: number; category: string; confidence: number };

// --- AUTH ---
function getToken(): string { return localStorage.getItem("access") || ""; }
function getAuthHeaders(): HeadersInit { const t = getToken(); return t ? { Authorization: `Bearer ${t}` } : {}; }
function withAuth(url: string): string {
  const t = getToken();
  return t ? url + (url.includes("?") ? "&" : "?") + `access_token=${encodeURIComponent(t)}` : url;
}

// --- API ---
function pickRedactedUrlFromJson(j: any): string | undefined { return j?.redacted?.url as string | undefined; }
async function fetchOriginalUrl(id: string, headers: HeadersInit) {
  const r = await fetch(withAuth(`${API_BASE}/videos/${id}/stream`), { headers });
  if (!r.ok) throw new Error(`stream failed: ${r.status}`);
  const { url } = await r.json();
  if (!url) throw new Error("no stream url");
  return url as string;
}
async function pollRedactedUrl(id: string, headers: HeadersInit, timeoutMs = 60_000) {
  const started = Date.now(); let attempt = 0;
  while (true) {
    const r = await fetch(withAuth(`${API_BASE}/redactions/download/${id}?profile_id=active&presigned=true`), { headers });
    if (r.status === 401) throw new Error("unauthorized");
    if (r.ok) {
      const j = await r.json().catch(() => ({}));
      const u = pickRedactedUrlFromJson(j);
      if (u) return u;
    } else if (r.status !== 404 && r.status < 500) {
      throw new Error(`unexpected_status_${r.status}`);
    }
    if (Date.now() - started > timeoutMs) throw new Error("redaction timeout");
    attempt++; await new Promise(res => setTimeout(res, Math.min(3000, 500 + attempt * 300)));
  }
}

// ---- helpers ----
const formatTime = (sec: number) => {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

export default function Player() {
  const { id = "" } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const startFiltered = useMemo(() => search.get("mode") === "censored", [search]);

  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [showWarning, setShowWarning] = useState(false);

  // FEEDBACK – only at the end
  const [showFeedbackCard, setShowFeedbackCard] = useState(false);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [feedback, setFeedback] = useState("");

  const [analysis, setAnalysis] = useState<AnalysisEvent[]>([]);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [durationSec, setDurationSec] = useState(0);
  const [censorMode, setCensorMode] = useState(startFiltered);
  const [volume, setVolume] = useState(0.7);
  const [muted, setMuted] = useState(false);

  // progress drag state
  const [dragging, setDragging] = useState(false);

  const headers = getAuthHeaders();

  // Require auth for filtered
  useEffect(() => {
    if (censorMode && !getToken()) {
      toast.error("You must sign in to use Filtered Mode.");
      setCensorMode(false);
    }
  }, [censorMode]);

  // Load video URL on mode/id change
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        toast.info(censorMode ? "Preparing filtered stream…" : "Loading original…");
        const url = censorMode ? await pollRedactedUrl(id, headers) : await fetchOriginalUrl(id, headers);
        if (!cancelled) {
          setVideoUrl(url);
          setLoading(false);
          toast.success("Video ready!");
        }
      } catch (e: any) {
        console.error(e);
        if (!cancelled) {
          setLoading(false);
          toast.error(
            e?.message === "unauthorized" ? "401 Unauthorized — please sign in." :
            e?.message === "redaction timeout" ? "Filtered stream could not be prepared (timeout)." :
            "Could not load video"
          );
        }
      }
    })();
    return () => { cancelled = true; };
  }, [id, censorMode]);

  // Time / duration tracking + volume sync
  useEffect(() => {
    const v = videoRef.current; if (!v) return;
    v.volume = volume; v.muted = muted;

    const onTime = () => setCurrentTimeMs(v.currentTime * 1000);
    const onLoaded = () => setDurationSec(v.duration || 0);
    const onEnded = () => {
      if (censorMode) setShowFeedbackCard(true); // only after ended
      setIsPlaying(false);
    };

    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onLoaded);
    v.addEventListener("ended", onEnded);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onLoaded);
      v.removeEventListener("ended", onEnded);
    };
  }, [volume, muted, censorMode]);

  const pct = durationSec ? Math.min(100, (currentTimeMs / (durationSec * 1000)) * 100) : 0;

  const handleAction = (action: "skip" | "blur" | "continue") => {
    setShowWarning(false);
    const v = videoRef.current; if (!v) return;
    if (action === "skip") {
      const now = currentTimeMs;
      const nextEvent = analysis.find(a => a.start > now);
      v.currentTime = nextEvent ? nextEvent.start / 1000 : v.currentTime + 2;
      toast.success("Scene skipped!");
    } else if (action === "blur") {
      toast.success("Scene blurred (demo)");
    } else {
      toast.info("Continuing normally");
    }
  };

  // Feedback button handlers
  const onFeedbackYes = () => setShowFeedbackCard(false);
  const onFeedbackNo  = () => setShowFeedbackDialog(true);
  const submitFeedback = async () => {
    try {
      await fetch(withAuth(`${API_BASE}/feedback/manual`), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ video_id: id, text: feedback }),
      });
      toast.success("Feedback submitted. Thank you!");
      setFeedback(""); setShowFeedbackDialog(false); setShowFeedbackCard(false);
    } catch {
      toast.error("Failed to send feedback");
    }
  };

  // Fullscreen
  const goFullscreen = () => {
    const root = containerRef.current || videoRef.current;
    if (!root) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      root.requestFullscreen({ navigationUI: "hide" as any }).catch(() => {});
    }
  };

  // progress seeking helpers
  const handleSeekPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const v = videoRef.current; if (!v || !durationSec) return;
    const bar = e.currentTarget;
    const rect = bar.getBoundingClientRect();
    const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));
    const seekTo = (clientX: number) => {
      const p = clamp((clientX - rect.left) / rect.width, 0, 1);
      v.currentTime = p * durationSec;
      setCurrentTimeMs(v.currentTime * 1000);
    };
    setDragging(true);
    seekTo(e.clientX);
    const move = (ev: PointerEvent) => seekTo(ev.clientX);
    const up   = () => { setDragging(false); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // --- LOADING OVERLAY (animation + info) ---
  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <style>{`
          .shine {
            background: linear-gradient(90deg,#fff 0%,#cbd5e1 50%,#fff 100%);
            -webkit-background-clip: text; background-clip: text; color: transparent;
            animation: shine 2.2s linear infinite;
            background-size: 200% 100%;
          }
          @keyframes shine { 0%{background-position:0% 50%} 100%{background-position:200% 50%} }
          .dots::after{content:"."; animation: dots 1.4s steps(4,end) infinite}
          @keyframes dots {0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}100%{content:""}}
          .eqbar{display:block;width:6px;height:10px;background:#fff;border-radius:3px;opacity:.9;
                 animation:eq 1s ease-in-out infinite}
          .eqbar+.eqbar{margin-left:6px}
          .delay-1{animation-delay:.1s}.delay-2{animation-delay:.2s}.delay-3{animation-delay:.3s}.delay-4{animation-delay:.4s}
          @keyframes eq {0%,100%{transform:scaleY(.3)}50%{transform:scaleY(1.2)}}
        `}</style>
        <div className="flex flex-col items-center gap-6 text-center px-6">
          <h2 className="text-2xl md:text-3xl font-semibold tracking-wide shine">
            Processing with your filters<span className="dots" />
          </h2>

          <div className="flex items-end gap-1 h-10">
            <span className="eqbar" />
            <span className="eqbar delay-1" />
            <span className="eqbar delay-2" />
            <span className="eqbar delay-3" />
            <span className="eqbar delay-4" />
          </div>

          <p className="text-sm md:text-base text-white/70 max-w-xl">
            This may take <strong>a few minutes</strong> depending on the video. Playback will start automatically when it’s ready.
          </p>

          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={() => setCensorMode(false)}>Watch original</Button>
            <Button variant="ghost" onClick={() => window.history.back()}>Go back</Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    // FULL-BLEED PLAYER
    <div ref={containerRef} className="h-screen w-screen bg-black overflow-hidden relative">

      {/* Back button – pastel */}
      <div className="absolute top-4 left-4 z-30">
        <button
          onClick={() => (history.length > 1 ? window.history.back() : (window.location.href = "/"))}
          className="px-3 py-2 rounded-xl backdrop-blur bg-white/10 hover:bg-white/15 text-white/90
                     border border-white/10 shadow-sm transition-colors"
          aria-label="Go back"
          title="Back"
        >
          <div className="flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" />
            <span className="text-sm">Back</span>
          </div>
        </button>
      </div>

      {/* video */}
      <video
        key={(censorMode ? "c" : "o") + ":" + videoUrl}
        ref={videoRef}
        src={videoUrl}
        crossOrigin="anonymous"
        className="absolute inset-0 w-full h-full object-contain bg-black"
        controls={false}
        playsInline
        controlsList="nodownload noplaybackrate nofullscreen"
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onClick={() => {
          const v = videoRef.current; if (!v) return;
          v.paused ? v.play() : v.pause();
        }}
      />

      {/* timeline (click & drag) */}
      <div className="absolute bottom-24 left-8 right-8 z-10 select-none">
        <div
          className={`relative h-2 rounded-full overflow-hidden ${dragging ? "ring-2 ring-white/20" : ""}`}
          style={{ backgroundColor: "rgba(255,255,255,0.12)" }}
          onPointerDown={handleSeekPointerDown}
        >
          <div
            className="absolute h-full transition-[width] duration-100 will-change-[width]"
            style={{ width: `${pct}%`, backgroundColor: "rgb(239 68 68)" }} // red-500
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-white/70">
          <span>{formatTime(currentTimeMs / 1000)}</span>
          <span>{formatTime(durationSec)}</span>
        </div>
      </div>

      {/* controls */}
      <div className="absolute bottom-8 left-8 right-8 z-20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              size="icon"
              variant="ghost"
              onClick={() => {
                const v = videoRef.current; if (!v) return;
                v.paused ? v.play() : v.pause();
              }}
              className="w-12 h-12"
            >
              {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
            </Button>

            <div className="flex items-center gap-2">
              {muted || volume === 0 ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
              <Slider
                value={[Math.round(volume * 100)]}
                onValueChange={(val) => {
                  const v = videoRef.current;
                  const vol = (val?.[0] ?? 70) / 100;
                  setVolume(vol);
                  if (v) { v.volume = vol; if (vol > 0 && v.muted) v.muted = false; }
                }}
                max={100}
                className="w-28"
              />
              <Button
                size="icon"
                variant="ghost"
                onClick={() => {
                  const v = videoRef.current; if (!v) return;
                  const newMuted = !(muted || v.muted);
                  setMuted(newMuted); v.muted = newMuted;
                }}
              >
                {muted || volume === 0 ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
              </Button>
            </div>

            <span className="text-sm text-muted-foreground tabular-nums">
              {formatTime(currentTimeMs / 1000)}{" / "}{formatTime(durationSec)}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <Button size="icon" variant="ghost" onClick={goFullscreen}>
              <Maximize className="w-5 h-5" />
            </Button>
          </div>
        </div>
      </div>

      {/* warning dialog */}
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

      {/* feedback card — only after ended in filtered mode */}
      {censorMode && showFeedbackCard && !showWarning && (
        <div className="absolute bottom-8 right-8 z-20 p-6 bg-card border border-border rounded-xl shadow-xl max-w-sm">
          <h3 className="font-semibold mb-2">Did the filtering work correctly?</h3>
          <div className="flex gap-3">
            <Button className="flex-1" onClick={onFeedbackYes}>
              <ThumbsUp className="w-4 h-4 mr-2" /> Yes
            </Button>
            <Button className="flex-1" variant="outline" onClick={onFeedbackNo}>
              <ThumbsDown className="w-4 h-4 mr-2" /> No
            </Button>
          </div>

          <Dialog open={showFeedbackDialog} onOpenChange={setShowFeedbackDialog}>
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
                <Button variant="secondary" onClick={() => setShowFeedbackDialog(false)}>Cancel</Button>
                <Button onClick={submitFeedback}>Send</Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </div>
  );
}
