// src/pages/Player.tsx
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Play, Pause, Volume2, VolumeX, Maximize, SkipForward,
  Eye, ThumbsUp, ThumbsDown, ArrowLeft
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Slider } from "../components/ui/slider";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog";
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

// --- URL helpers ---
const isPlayableUrl = (u: unknown): u is string =>
  typeof u === "string" && (/^https?:\/\//i.test(u) || u.startsWith("/"));

function pickRedactedUrlFromJson(j: any): string | undefined {
  if (isPlayableUrl(j?.redacted?.url)) return String(j.redacted.url);
  if (isPlayableUrl(j?.stream_url))    return String(j.stream_url);
  if (isPlayableUrl(j?.url))           return String(j.url);
  if (isPlayableUrl(j?.downloadUrl))   return String(j.downloadUrl);
  if (isPlayableUrl(j?.storage_key))   return String(j.storage_key);
  return undefined;
}

// --- API ---
async function fetchOriginalUrl(id: string, headers: HeadersInit) {
  const r = await fetch(withAuth(`${API_BASE}/videos/${id}/stream`), { headers });
  if (!r.ok) throw new Error(`stream failed: ${r.status}`);
  const data = await r.json();
  const url = data?.url;
  if (!isPlayableUrl(url)) throw new Error("no stream url");
  return url as string;
}

/**
 * Sansürlü akış istenir. Eğer backend “no filters” (veya sansüre gerek yok) dönerse
 * özel bir hata fırlatırız: Error("no_filters").
 */
async function pollRedactedUrl(id: string, headers: HeadersInit, timeoutMs = 60_000) {
  const started = Date.now(); let attempt = 0;
  while (true) {
    const r = await fetch(
      withAuth(`${API_BASE}/redactions/download/${id}?profile_id=active&presigned=true`),
      { headers }
    );
    if (r.status === 401) throw new Error("unauthorized");

    if (r.ok) {
      const j = await r.json().catch(() => ({}));

      // backend açıkça işaret ettiyse
      if (j?.no_filters === true || j?.reason === "no_filters" || j?.redacted?.reason === "no_filters") {
        throw new Error("no_filters");
      }

      const u = pickRedactedUrlFromJson(j);
      if (u) return u;

      // 200 ama redacted url yoksa; çoğu backend bunu “sansüre gerek yok” olarak verir
      throw new Error("no_filters");
    }

    // 204 de “sansüre gerek yok” olarak kabul
    if (r.status === 204) throw new Error("no_filters");

    if (r.status !== 404 && r.status < 500) {
      throw new Error(`unexpected_status_${r.status}`);
    }
    if (Date.now() - started > timeoutMs) throw new Error("redaction timeout");

    attempt++;
    await new Promise(res => setTimeout(res, Math.min(3000, 500 + attempt * 300)));
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
  const barRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [showWarning, setShowWarning] = useState(false);

  // FEEDBACK – only at the end
  const [showFeedbackCard, setShowFeedbackCard] = useState(false);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [feedback, setFeedback] = useState("");

  const [analysis] = useState<AnalysisEvent[]>([]);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [durationSec, setDurationSec] = useState(0);
  const [censorMode, setCensorMode] = useState(startFiltered);
  const [volume, setVolume] = useState(0.7);
  const [muted, setMuted] = useState(false);

  // SEEK / SCRUB
  const [scrubbing, setScrubbing] = useState(false);
  const [wasPlayingBeforeDrag, setWasPlayingBeforeDrag] = useState(false);
  const [bufferedSec, setBufferedSec] = useState(0);

  // ---- AUTO-HIDE CHROME
  const [showChrome, setShowChrome] = useState(true);
  const hideTimerRef = useRef<number | null>(null);

  const headers = getAuthHeaders();

  // auth check
  useEffect(() => {
    if (censorMode && !getToken()) {
      toast.error("You must sign in to use Filtered Mode.");
      setCensorMode(false);
    }
  }, [censorMode]);

  // load url (+ no-filters guard)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        toast.info(censorMode ? "Preparing filtered stream…" : "Loading original…");

        const url = censorMode
          ? await pollRedactedUrl(id, headers)
          : await fetchOriginalUrl(id, headers);

        if (!cancelled) {
          setVideoUrl(url);
          setLoading(false);
          toast.success("Video ready!");
        }
      } catch (e: any) {
        console.error(e);
        if (cancelled) return;

        setLoading(false);

        if (e?.message === "no_filters") {
          // İSTENEN DAVRANIŞ: uyar, player'a girme → geri dön
          toast.warning("Sansürlü izleme için önce tercihlerinizi oluşturmanız gerekiyor.");
          if (history.length > 1) window.history.back();
          else window.location.href = "/";
          return;
        }

        toast.error(
          e?.message === "unauthorized" ? "401 Unauthorized — please sign in." :
          e?.message === "redaction timeout" ? "Filtered stream could not be prepared (timeout)." :
          "Could not load video"
        );
        setVideoUrl("");
      }
    })();
    return () => { cancelled = true; };
  }, [id, censorMode]);

  // duration & time tracking
  useEffect(() => {
    const v = videoRef.current; if (!v) return;
    v.volume = volume; v.muted = muted;

    const updateBuffered = () => {
      try {
        const end = v.buffered?.length ? v.buffered.end(v.buffered.length - 1) : 0;
        setBufferedSec(isFinite(end) ? end : 0);
      } catch {}
    };

    const updateDuration = () => {
      let d = v.duration;
      if (!isFinite(d) || !d) {
        try { if (v.seekable?.length) d = v.seekable.end(v.seekable.length - 1); } catch {}
      }
      if (!isFinite(d) || !d) {
        try { if (v.buffered?.length) d = v.buffered.end(v.buffered.length - 1); } catch {}
      }
      setDurationSec(isFinite(d) ? d : 0);
      updateBuffered();
    };

    const onTime = () => {
      setCurrentTimeMs(v.currentTime * 1000);
      if (!durationSec) updateDuration();
    };

    const onLoadedMeta = () => updateDuration();
    const onDurationChange = () => updateDuration();
    const onCanPlay = () => updateDuration();
    const onProgress = () => updateBuffered();
    const onEnded = () => {
      if (censorMode) setShowFeedbackCard(true);
      setIsPlaying(false);
      setShowChrome(true);
      clearHideTimer();
    };
    const onError = () => {
      const err: any = (v as any).error;
      console.error("Video element error:", err);
      toast.error("Video file failed to load.");
    };

    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onLoadedMeta);
    v.addEventListener("durationchange", onDurationChange);
    v.addEventListener("canplay", onCanPlay);
    v.addEventListener("progress", onProgress);
    v.addEventListener("ended", onEnded);
    v.addEventListener("error", onError);

    updateDuration();

    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onLoadedMeta);
      v.removeEventListener("durationchange", onDurationChange);
      v.removeEventListener("canplay", onCanPlay);
      v.removeEventListener("progress", onProgress);
      v.removeEventListener("ended", onEnded);
      v.removeEventListener("error", onError);
    };
  }, [volume, muted, censorMode, durationSec]);

  const playedPct = durationSec ? Math.min(100, (currentTimeMs / 1000 / durationSec) * 100) : 0;

  // ---- AUTO-HIDE helpers
  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const scheduleHide = useCallback(() => {
    clearHideTimer();
    const v = videoRef.current;
    const shouldKeepVisible = scrubbing || !v || v.paused;
    if (shouldKeepVisible) return;
    hideTimerRef.current = window.setTimeout(() => {
      setShowChrome(false);
    }, 2000) as unknown as number;
  }, [scrubbing, clearHideTimer]);

  const bumpActivity = useCallback(() => {
    setShowChrome(true);
    scheduleHide();
  }, [scheduleHide]);

  // global activity listeners
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    const onMove = () => bumpActivity();
    const onKey = (e: KeyboardEvent) => {
      const keys = [" ", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "f", "F"];
      if (keys.includes(e.key)) bumpActivity();
    };
    const onClick = () => bumpActivity();
    const onTouch = () => bumpActivity();

    root.addEventListener("mousemove", onMove);
    root.addEventListener("pointermove", onMove);
    root.addEventListener("click", onClick);
    root.addEventListener("touchstart", onTouch, { passive: true });
    window.addEventListener("keydown", onKey);

    scheduleHide();

    return () => {
      root.removeEventListener("mousemove", onMove);
      root.removeEventListener("pointermove", onMove);
      root.removeEventListener("click", onClick);
      root.removeEventListener("touchstart", onTouch);
      window.removeEventListener("keydown", onKey);
      clearHideTimer();
    };
  }, [bumpActivity, scheduleHide, clearHideTimer]);

  const onPlayClick = () => {
    const v = videoRef.current; if (!v) return;
    if (v.paused) v.play();
    else v.pause();
  };

  // skip/blur demo
  const handleAction = (action: "skip" | "blur" | "continue") => {
    setShowWarning(false);
    const v = videoRef.current; if (!v) return;
    if (action === "skip") {
      v.currentTime = Math.min(v.duration || v.currentTime + 2, v.currentTime + 10);
      toast.success("Scene skipped!");
    } else if (action === "blur") {
      toast.success("Scene blurred (demo)");
    } else {
      toast.info("Continuing normally");
    }
  };

  // feedback
  const onFeedbackYes = () => setShowFeedbackCard(false);
  const onFeedbackNo  = () => setShowFeedbackDialog(true);
  const submitFeedback = async () => {
    try {
      await fetch(withAuth(`${API_BASE}/feedback/manual`), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ video_id: id, text: feedback }),
      });
      toast.success("Feedback submitted. Thank you!");
      setFeedback(""); setShowFeedbackDialog(false); setShowFeedbackCard(false);
    } catch {
      toast.error("Failed to send feedback");
    }
  };

  // fullscreen
  const goFullscreen = () => {
    const root = containerRef.current || videoRef.current;
    if (!root) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      root.requestFullscreen({ navigationUI: "hide" as any }).catch(() => {});
    }
  };

  // --- SCRUB HELPERS
  const seekAtClientX = (clientX: number) => {
    const v = videoRef.current, bar = barRef.current;
    if (!v || !bar || !durationSec) return;
    const rect = bar.getBoundingClientRect();
    const p = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    v.currentTime = p * durationSec;
    setCurrentTimeMs(v.currentTime * 1000);
  };

  const startScrub = (clientX: number) => {
    if (!durationSec) return;
    const v = videoRef.current;
    if (v) { setWasPlayingBeforeDrag(!v.paused); v.pause(); }
    setScrubbing(true);
    setShowChrome(true);
    seekAtClientX(clientX);
    clearHideTimer();

    const onMovePointer = (ev: PointerEvent) => { ev.preventDefault(); seekAtClientX(ev.clientX); };
    const onUpPointer = () => {
      setScrubbing(false);
      window.removeEventListener("pointermove", onMovePointer);
      window.removeEventListener("pointerup", onUpPointer);
      const vv = videoRef.current;
      if (vv && wasPlayingBeforeDrag) vv.play().then(() => scheduleHide()).catch(() => {});
      else setShowChrome(true);
    };
    window.addEventListener("pointermove", onMovePointer, { passive: false });
    window.addEventListener("pointerup", onUpPointer, { once: true });

    const onMouseMove = (ev: MouseEvent) => { ev.preventDefault(); seekAtClientX(ev.clientX); };
    const onMouseUp = () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp, { once: true });

    const onTouchMove = (ev: TouchEvent) => {
      if (ev.touches?.length) { ev.preventDefault(); seekAtClientX(ev.touches[0].clientX); }
    };
    const onTouchEnd = () => {
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd, { once: true, passive: true });
  };

  // --- LOADING OVERLAY ---
  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <style>{`
          .shine{background:linear-gradient(90deg,#fff 0%,#cbd5e1 50%,#fff 100%);-webkit-background-clip:text;background-clip:text;color:transparent;animation:shine 2.2s linear infinite;background-size:200% 100%}
          @keyframes shine{0%{background-position:0% 50%}100%{background-position:200% 50%}}
          .dots::after{content:".";animation:dots 1.4s steps(4,end) infinite}
          @keyframes dots{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}100%{content:""}}
          .eqbar{display:block;width:6px;height:10px;background:#fff;border-radius:3px;opacity:.9;animation:eq 1s ease-in-out infinite}
          .eqbar+.eqbar{margin-left:6px}.delay-1{animation-delay:.1s}.delay-2{animation-delay:.2s}.delay-3{animation-delay:.3s}.delay-4{animation-delay:.4s}
          @keyframes eq{0%,100%{transform:scaleY(.3)}50%{transform:scaleY(1.2)}}
        `}</style>
        <div className="flex flex-col items-center gap-6 text-center px-6">
          <h2 className="text-2xl md:text-3xl font-semibold tracking-wide shine">
            Processing with your filters<span className="dots" />
          </h2>
          <div className="flex items-end gap-1 h-10">
            <span className="eqbar" /><span className="eqbar delay-1" /><span className="eqbar delay-2" />
            <span className="eqbar delay-3" /><span className="eqbar delay-4" />
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
    <div
      ref={containerRef}
      className={`h-[100svh] w-full bg-black overflow-hidden relative ${(!showChrome && isPlaying) ? "cursor-none" : ""}`}
      onMouseMove={() => bumpActivity()}
      onClick={() => bumpActivity()}
      onTouchStart={() => bumpActivity()}
    >
      {/* Back */}
      <div
        className={`absolute top-4 left-4 z-40 transition-all duration-300
          ${showChrome ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-2 pointer-events-none"}`}
      >
        <button
          onClick={() => (history.length > 1 ? window.history.back() : (window.location.href = "/"))}
          className="px-3 py-2 rounded-xl backdrop-blur bg-white/10 hover:bg-white/15 text-white/90 border border-white/10 shadow-sm transition-colors"
          aria-label="Go back" title="Back"
        >
          <div className="flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" /><span className="text-sm">Back</span>
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
        preload="metadata"
        onLoadedMetadata={(e) => {
          const v = e.currentTarget;
          const d = isFinite(v.duration) && v.duration ? v.duration : 0;
          if (d) setDurationSec(d);
        }}
        controlsList="nodownload noplaybackrate nofullscreen"
        onPlay={() => {
          setIsPlaying(true);
          scheduleHide();
        }}
        onPause={() => {
          setIsPlaying(false);
          setShowChrome(true);
          clearHideTimer();
        }}
        onClick={() => {
          const v = videoRef.current; if (!v) return;
          v.paused ? v.play() : v.pause();
        }}
        onError={() => {
          toast.error("Video file failed to load.");
        }}
      />

      {/* timeline */}
      <div
        className={`absolute bottom-24 md:bottom-24 left-4 right-4 md:left-8 md:right-8 z-40 select-none safe-bottom
          transition-all duration-300 ${showChrome ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6 pointer-events-none"}`}
      >
        <div
          ref={barRef}
          role="slider"
          aria-valuemin={0}
          aria-valuemax={Math.floor(durationSec || 0)}
          aria-valuenow={Math.floor(currentTimeMs / 1000)}
          className={`relative h-2 md:h-3 rounded-full overflow-hidden cursor-pointer ${scrubbing ? "ring-2 ring-white/20" : ""}`}
          style={{ backgroundColor: "rgba(255,255,255,0.10)", touchAction: "none" as any }}
          onPointerDown={(e) => startScrub(e.clientX)}
          onMouseDown={(e) => startScrub(e.clientX)}
          onTouchStart={(e) => { if (e.touches?.length) startScrub(e.touches[0].clientX); }}
          onClick={(e) => {
            if (scrubbing) return;
            const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
            const p = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
            const v = videoRef.current;
            if (v && durationSec) v.currentTime = p * durationSec;
          }}
        >
          {/* buffered */}
          <div
            className="absolute inset-y-0 left-0"
            style={{
              width: `${bufferedSec && durationSec ? (bufferedSec / durationSec) * 100 : 0}%`,
              backgroundColor: "rgba(255,255,255,0.25)"
            }}
          />
          {/* played */}
          <div
            className="absolute inset-y-0 left-0 transition-[width,background-color] duration-100 will-change-[width]"
            style={{
              width: `${playedPct}%`,
              backgroundColor: playedPct >= 90 ? "rgb(249 115 22)" : "rgb(239 68 68)"
            }}
          />
          {/* knob */}
          <div
            className="absolute -top-2 md:-top-1.5 h-5 w-5 md:h-6 md:w-6 rounded-full bg-white/90 shadow-md"
            style={{ left: `calc(${playedPct}% - 12px)` }}
          />
        </div>

        <div className="mt-2 flex items-center justify-between text-xs text-white/70">
          <span>{formatTime(currentTimeMs / 1000)}</span>
          <span>{formatTime(durationSec)}</span>
        </div>
      </div>

      {/* controls */}
      <div
        className={`absolute bottom-4 md:bottom-8 left-4 right-4 md:left-8 md:right-8 z-30
          transition-all duration-300 ${showChrome ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6 pointer-events-none"}`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              size="icon"
              variant="ghost"
              onClick={onPlayClick}
              className="w-12 h-12 md:w-12 md:h-12"
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
                  bumpActivity();
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
                  bumpActivity();
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

      {/* warning */}
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

      {/* feedback (end only) */}
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
