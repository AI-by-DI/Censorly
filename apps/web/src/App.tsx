// src/App.tsx
import React, { useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  Link,
} from "react-router-dom";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard"; // varsa kullan
import Profile from "./pages/Profile";
import Index from "./pages/Index";
import Player from "./pages/Player";
import VideoDetail from "./pages/VideoDetail";
import NotFound from "./pages/NotFound";

// basit auth kontrolü (JWT 'access' key)
function useAuthState() {
  const [authed, setAuthed] = useState(!!localStorage.getItem("access"));

  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === "access") setAuthed(!!localStorage.getItem("access"));
    }
    function onAuthChanged() {
      setAuthed(!!localStorage.getItem("access"));
    }
    window.addEventListener("storage", onStorage);
    window.addEventListener("auth:changed", onAuthChanged);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("auth:changed", onAuthChanged);
    };
  }, []);

  return authed;
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const authed = useAuthState();
  const location = useLocation();
  if (!authed) return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}

function PublicOnly({ children }: { children: React.ReactNode }) {
  const authed = useAuthState();
  if (authed) return <Navigate to="/index" replace />;
  return <>{children}</>;
}

export default function App() {
  const initialAuthed = useMemo(() => !!localStorage.getItem("access"), []);
  const authed = useAuthState();

  return (
    <BrowserRouter>
      {/* Basit nav (geçici) */}
      {authed && (
        <nav className="p-3 flex gap-4 border-b border-border">
          <Link to="/index">Home</Link>
          <Link to="/profile">Profile</Link>
        </nav>
      )}

      <Routes>
        {/* Köke geldiğinde */}
        <Route
          path="/"
          element={<Navigate to={initialAuthed ? "/index" : "/login"} replace />}
        />

        {/* Giriş sayfası */}
        <Route
          path="/login"
          element={
            <PublicOnly>
              <Login />
            </PublicOnly>
          }
        />

        {/* Ana sayfa (dashboard yerine lovable'ın Index sayfası) */}
        <Route
          path="/index"
          element={
            <ProtectedRoute>
              <Index />
            </ProtectedRoute>
          }
        />

        {/* Profil */}
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Profile />
            </ProtectedRoute>
          }
        />

        {/* Video detay */}
        <Route
          path="/video/:id"
          element={
            <ProtectedRoute>
              <VideoDetail />
            </ProtectedRoute>
          }
        />

        {/* Player */}
        <Route
          path="/player/:id"
          element={
            <ProtectedRoute>
              <Player />
            </ProtectedRoute>
          }
        />

        {/* 404 */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
