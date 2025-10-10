import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ensureActiveProfile } from "../lib/api";

export default function Dashboard() {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        await ensureActiveProfile(); // tek profil: yoksa oluştur
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div style={{ padding: 24 }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <h1 style={{ margin: 0 }}>Censorly</h1>
        <Link
          to="/profile"
          style={{
            textDecoration: "none",
            padding: "8px 12px",
            border: "1px solid #333",
            borderRadius: 8,
          }}
        >
          Profili Aç
        </Link>
      </header>

      <section>
        {loading ? (
          <p>Yükleniyor…</p>
        ) : (
          <p>
            Hoş geldin! Sansür tercihlerini yönetmek için{" "}
            <Link to="/profile">Profil</Link> sayfasına gidebilirsin.
          </p>
        )}
      </section>
    </div>
  );
}
