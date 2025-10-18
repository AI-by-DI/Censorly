// src/App.tsx
import React, { useEffect, useMemo, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";

import Login from "./pages/Login";
import Profile from "./pages/Profile";
import Index from "./pages/Index";
import Player from "./pages/Player";
import VideoDetail from "./pages/VideoDetail";
import NotFound from "./pages/NotFound";
import Landing from "./pages/Landing";
import ForgotPasswordPage from "./pages/ForgotPassword";


function useAuthState() {
  const [authed, setAuthed] = useState(!!localStorage.getItem("access"));
  useEffect(() => {
    const onStorage = (e: StorageEvent) => { if (e.key === "access") setAuthed(!!localStorage.getItem("access")); };
    const onAuthChanged = () => setAuthed(!!localStorage.getItem("access"));
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
  const authed = useAuthState();

  return (
    <BrowserRouter>
      <Routes>
        {/* Root artık koşullu yönlendiriyor */}
        <Route path="/" element={<Navigate to={authed ? "/index" : "/landing"} replace />} />

        {/* Landing ayrı route */}
        <Route path="/landing" element={<Landing />} />

        <Route
          path="/login"
          element={
            <PublicOnly>
              <Login />
            </PublicOnly>
          }
        />

        <Route
          path="/index"
          element={
            <ProtectedRoute>
              <Index />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Profile />
            </ProtectedRoute>
          }
        />
        <Route
          path="/video/:id"
          element={
            <ProtectedRoute>
              <VideoDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/player/:id"
          element={
            <ProtectedRoute>
              <Player />
            </ProtectedRoute>
          }
        />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />



        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
