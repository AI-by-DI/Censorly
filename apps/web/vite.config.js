import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import dotenv from "dotenv";

// 🌍 1️⃣ Ortak .env (root’taki)
dotenv.config({ path: path.resolve(__dirname, "../../.env") });
// 🌍 2️⃣ Uygulamaya özel .env (apps/web içinde)
dotenv.config();

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    // 💡 Lovable'ın componentTagger eklentisi varsa buraya eklenebilir.
    // mode === "development" && componentTagger(),
  ].filter(Boolean),

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },

  server: {
    host: true,            // LAN erişimine açık
    port: 5173,            // senin daha önce kullandığın port
    strictPort: true,      // başka port’a fallback yapmaz
    hmr: { clientPort: 5173 }, // Hot Module Reload düzgün çalışsın
  },

  define: {
    // 🌱 Vite ortam değişkenlerini build zamanında inject eder
    "process.env": process.env,
  },
}));

