import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 開発中は Vite（:5173）で画面を配信し、API と練習ファイルは FastAPI（:8765）に転送する
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/files": "http://127.0.0.1:8765",
    },
  },
});
