import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
} from "react-router-dom";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

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
  return (
    <BrowserRouter>
      <Routes>
        {/* Kök path'te durumuna göre yönlendir */}
        <Route path="/" element={<Navigate to={initialAuthed ? "/dashboard" : "/login"} replace />} />

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

        {/* 404 → duruma göre yönlendir */}
        <Route path="*" element={<Navigate to={initialAuthed ? "/dashboard" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}

const rootEl = document.getElementById("root");
ReactDOM.createRoot(rootEl).render(<App />);
