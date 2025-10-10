// src/index.jsx
import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  Link,
} from "react-router-dom";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Profile from "./pages/Profile"; // ⬅️ eklendi

/** Basit auth state (localStorage 'access' anahtarını izler) */
function useAuthState() {
  const [authed, setAuthed] = useState(!!localStorage.getItem("access"));

  useEffect(() => {
    // Diğer sekmelerde değişiklik olursa:
    function onStorage(e) {
      if (e.key === "access") {
        setAuthed(!!localStorage.getItem("access"));
      }
    }
    window.addEventListener("storage", onStorage);

    // Aynı sekmede login/logout sonrası tetiklemek istersen:
    function onAuthChanged() {
      setAuthed(!!localStorage.getItem("access"));
    }
    window.addEventListener("auth:changed", onAuthChanged);

    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("auth:changed", onAuthChanged);
    };
  }, []);

  return authed;
}

/** Korumalı rota: authed değilse /login'e yollar */
function ProtectedRoute({ children }) {
  const authed = useAuthState();
  const location = useLocation();
  if (!authed) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children;
}

/** Public rota: authed ise dashboard'a yollar */
function PublicOnly({ children }) {
  const authed = useAuthState();
  if (authed) return <Navigate to="/dashboard" replace />;
  return children;
}

function App() {
  // İlk yüklemede kök yönlendirme için tek seferlik hesap
  const initialAuthed = useMemo(() => !!localStorage.getItem("access"), []);
  const authed = useAuthState(); // sadece nav göstermek için

  return (
    <BrowserRouter>
      {/* Authed isen basit bir nav gösterelim (yapıyı bozmadan) */}
      {authed && (
        <nav style={{ padding: 12, display: "flex", gap: 12, borderBottom: "1px solid #333" }}>
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/profile">Profile</Link>
        </nav>
      )}

      <Routes>
        {/* Kök path'te durumuna göre yönlendir */}
        <Route
          path="/"
          element={<Navigate to={initialAuthed ? "/dashboard" : "/login"} replace />}
        />

        {/* Giriş sayfası: authed ise /dashboard'a at */}
        <Route
          path="/login"
          element={
            <PublicOnly>
              <Login />
            </PublicOnly>
          }
        />

        {/* Dashboard: korumalı */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />

        {/* Profile: korumalı */}
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Profile />
            </ProtectedRoute>
          }
        />

        {/* 404 → duruma göre yönlendir */}
        <Route
          path="*"
          element={<Navigate to={initialAuthed ? "/dashboard" : "/login"} replace />}
        />
      </Routes>
    </BrowserRouter>
  );
}

const rootEl = document.getElementById("root");
ReactDOM.createRoot(rootEl).render(<App />);
