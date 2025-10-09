import { useEffect, useState } from "react";
import { authApi } from "../lib/api";
import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const nav = useNavigate();
  const [me, setMe] = useState<any>(null);

  useEffect(() => {
    authApi.me().then(setMe).catch(() => {
      nav("/login");
    });
  }, [nav]);

  const logout = async () => {
    await authApi.logout();
    nav("/login");
  };

  return (
    <div style={{ maxWidth: 720, margin: "40px auto" }}>
      <h2>Dashboard</h2>
      {me ? (
        <>
          <div>Hoş geldin, {me.email}</div>
          <button onClick={logout} style={{ marginTop: 12 }}>Çıkış</button>
        </>
      ) : (
        <div>Yükleniyor…</div>
      )}
    </div>
  );
}
