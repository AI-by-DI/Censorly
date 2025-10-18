import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import dotenv from "dotenv";

// 1) root .env
dotenv.config({ path: path.resolve(__dirname, "../../.env") });
// 2) app .env
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
    host: true,
    port: 5173,
    strictPort: true,
    hmr: { clientPort: 5173 },
  },
  define: {
    "process.env": process.env,
  },
}));