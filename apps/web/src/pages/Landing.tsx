// src/pages/Landing.tsx
import Footer from "../components/Footer";
import { Button } from "../components/ui/button";
import { useNavigate, Link } from "react-router-dom";
import { useState } from "react";

export default function Landing() {
  const navigate = useNavigate();
  const [mx, setMx] = useState(0);
  const [my, setMy] = useState(0);

  return (
    <div
      className="relative min-h-[100svh] w-full text-white overflow-hidden"
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const x = ((e.clientX - r.left) / r.width) * 2 - 1;
        const y = ((e.clientY - r.top) / r.height) * 2 - 1;
        setMx(x);
        setMy(y);
      }}
    >
      {/* KEYFRAMES & HELPERS */}
      <style>{`
        @keyframes kenburns {
          0%   { transform: scale(1.06) translate3d(-2%, -1%, 0); }
          50%  { transform: scale(1.10) translate3d(1%, 2%, 0); }
          100% { transform: scale(1.06) translate3d(-2%, -1%, 0); }
        }
        @keyframes aurora {
          0%{ background-position: 0% 50% }
          50%{ background-position: 100% 50% }
          100%{ background-position: 0% 50% }
        }
        @keyframes float1 {
          0%{ transform: translateY(0) translateX(0) }
          50%{ transform: translateY(-20px) translateX(10px) }
          100%{ transform: translateY(0) translateX(0) }
        }
        @keyframes float2 {
          0%{ transform: translateY(0) translateX(0) }
          50%{ transform: translateY(-16px) translateX(-12px) }
          100%{ transform: translateY(0) translateX(0) }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translate3d(0, 10px, 0); }
          to   { opacity: 1; transform: translate3d(0, 0, 0); }
        }
        .animate-fadeUp { animation: fadeUp .7s ease-out both; }
        .kb { animation: kenburns 30s ease-in-out infinite; will-change: transform; }
        @media (prefers-reduced-motion: reduce) { .kb { animation: none !important; } }
        .aurora {
          background: radial-gradient(1200px 600px at 20% -10%, rgba(244,63,94,.18), transparent 60%),
                      radial-gradient(1000px 600px at 110% 0%, rgba(14,165,233,.12), transparent 60%),
                      radial-gradient(900px 500px at -10% 110%, rgba(234,179,8,.13), transparent 60%);
          background-size: 200% 200%;
          animation: aurora 18s ease-in-out infinite;
          pointer-events: none;
        }
        .grain {
          background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120' viewBox='0 0 120 120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/><feComponentTransfer><feFuncA type='table' tableValues='0 0 0 .04 .08 0'/></feComponentTransfer></filter><rect width='120' height='120' filter='url(%23n)'/></svg>");
          opacity:.35; mix-blend-mode: overlay; pointer-events: none;
        }
      `}</style>

      {/* BACKGROUND */}
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat kb"
        style={{ backgroundImage: "url('/landing.jpg')" }}
        aria-hidden
      />
      <div className="absolute inset-0 aurora opacity-[.15]" />
      
      <div className="absolute inset-0 grain" />

      {/* FLOATING BOKEH */}
      <div className="absolute inset-0 pointer-events-none">
        <span className="absolute w-40 h-40 rounded-full blur-3xl bg-white/6" style={{ top: "18%", left: "12%", animation: "float1 10s ease-in-out infinite" }} />
        <span className="absolute w-32 h-32 rounded-full blur-3xl bg-red-400/10" style={{ top: "30%", right: "18%", animation: "float2 12s ease-in-out infinite" }} />
        <span className="absolute w-48 h-48 rounded-full blur-3xl bg-amber-300/10" style={{ bottom: "12%", left: "22%", animation: "float2 14s ease-in-out infinite" }} />
        <span className="absolute w-36 h-36 rounded-full blur-3xl bg-sky-300/10" style={{ bottom: "18%", right: "12%", animation: "float1 16s ease-in-out infinite" }} />
      </div>

      {/* BRAND (sol üst) */}
      <div className="absolute top-4 left-4 md:top-6 md:left-8 z-[60] select-none">
        <h1
          onClick={() => navigate("/")}
          title="Go home"
          className="text-4xl md:text-5xl font-extrabold tracking-tight cursor-pointer
                     transition-all duration-300 drop-shadow-[0_2px_8px_rgba(0,0,0,0.4)]
                     hover:text-red-500 hover:scale-[1.04]"
        >
          Censorly
        </h1>
      </div>

      {/* HERO */}
      <main className="relative z-30 h-full w-full">
        <div className="h-full w-full flex items-start justify-center pt-[22vh] md:pt-[26vh] lg:pt-[28vh]">
          <section
            className="px-6 text-center max-w-4xl animate-fadeUp"
            style={{ transform: `translate3d(${mx * 3}px, ${my * 2}px, 0)`, willChange: "transform" }}
          >
            <h2
              className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight"
              style={{ lineHeight: 1.1 }}
            >
              Filter Wisely, <span className="text-red-500">Watch Freely</span>.
            </h2>

            <p className="mt-5 text-base md:text-lg text-white/85">
              Your movies. Your rules. Powered by AI.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row gap-3 sm:gap-4 justify-center px-4">
              <Button asChild className="w-full sm:w-auto px-8 py-4 text-base sm:text-lg bg-white/10 hover:bg-white/15 border border-white/20">
                <Link to="/login?tab=login">Sign In</Link>
              </Button>
              <Button asChild className="w-full sm:w-auto px-8 py-4 text-base sm:text-lg bg-red-600 hover:bg-red-700">
                <Link to="/login?tab=register">Get Started</Link>
              </Button>
            </div>
          </section>
        </div>
      </main>

      {/* FOOTER */}
      <div className="absolute bottom-0 left-0 right-0 z-30 safe-bottom">
        <Footer />
      </div>
    </div>
  );
}
