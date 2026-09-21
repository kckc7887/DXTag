import { defineConfig } from "vite";

const lxnsProxy = {
  "/lxns-api": {
    target: "https://maimai.lxns.net",
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/lxns-api/, "/api/v0/maimai"),
  },
  "/lxns-chart": {
    target: "https://assets2.lxns.net",
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/lxns-chart/, "/maimai/chart"),
  },
};

export default defineConfig({
  base: "/",
  publicDir: "public",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 4173,
    host: true,
    proxy: lxnsProxy,
  },
  preview: {
    port: 4173,
    host: true,
    proxy: lxnsProxy,
  },
});
