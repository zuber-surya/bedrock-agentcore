import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/chat": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
});
