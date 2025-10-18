import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, X } from "lucide-react";
import { useCensorStore } from "../store/censorStore";

const API_BASE = import.meta.env.VITE_API_BASE as string;

type VideoLite = { id: string; title: string; poster_url?: string | null };

export default function SearchBox() {
  const { enabled } = useCensorStore();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<VideoLite[]>([]);
  const acRef = useRef<AbortController | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  // dışarı tıklayınca menüyü kapat
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // arama – debounce + abort
  useEffect(() => {
    if (!q.trim()) { setItems([]); return; }
    setLoading(true);
    acRef.current?.abort();
    const ac = new AbortController(); acRef.current = ac;

    const t = setTimeout(async () => {
      try {
        // 1) backend q destekliyorsa:
        const url = `${API_BASE}/videos?limit=20&q=${encodeURIComponent(q.trim())}`;
        let r = await fetch(url, { signal: ac.signal });
        let data: VideoLite[] | undefined;

        if (r.ok) {
          data = await r.json();
        } else {
          // 2) fallback: full list → client-side filter
          r = await fetch(`${API_BASE}/videos?limit=200`, { signal: ac.signal });
          const all: VideoLite[] = await r.json();
          const ql = q.trim().toLowerCase();
          data = all.filter(v => (v.title || "").toLowerCase().includes(ql)).slice(0, 20);
        }

        setItems((data || []).map(v => ({
          id: v.id,
          title: v.title || "Untitled",
          poster_url: v.poster_url || null,
        })));
        setOpen(true);
      } catch { /* aborted or network */ }
      finally { setLoading(false); }
    }, 300);

    return () => clearTimeout(t);
  }, [q]);

  const goTo = (id: string) => {
    setOpen(false);
    navigate(enabled ? `/player/${id}?mode=censored` : `/player/${id}?mode=original`);
  };

  const placeholder = useMemo(
    () => "Search movies and series…",
    []
  );

  return (
    <div ref={boxRef} className="relative w-full max-w-xl">
      <div className="flex items-center gap-2 rounded-full bg-muted/50 px-4 py-2 ring-1 ring-border">
        <Search className="w-4 h-4 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => q && setOpen(true)}
          placeholder={placeholder}
          className="w-full bg-transparent outline-none text-sm"
        />
        {q && (
          <button
            aria-label="Clear"
            onClick={() => { setQ(""); setItems([]); }}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* dropdown */}
      {open && (q || loading) && (
        <div className="absolute mt-2 w-full rounded-xl bg-popover border border-border shadow-xl overflow-hidden z-50">
          {loading ? (
            <div className="px-4 py-3 text-sm text-muted-foreground">Searching…</div>
          ) : items.length === 0 ? (
            <div className="px-4 py-3 text-sm text-muted-foreground">No results</div>
          ) : (
            <ul className="max-h-[60vh] overflow-auto">
              {items.map(v => (
                <li
                  key={v.id}
                  onClick={() => goTo(v.id)}
                  className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-muted/60"
                >
                  <img
                    src={v.poster_url || "/movie-1.jpg"}
                    alt={v.title}
                    className="w-10 h-14 object-cover rounded-md bg-muted"
                    loading="lazy"
                  />
                  <span className="text-sm">{v.title}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
