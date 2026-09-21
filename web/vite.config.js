import { defineConfig } from "vite";

export default defineConfig({
  base: process.env.GITHUB_PAGES_BASE || "/DXTag/",
  publicDir: "public",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 4173,
    host: true,
  },
});
