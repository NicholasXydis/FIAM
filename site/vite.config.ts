import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// The site, or with --mode film the ad, each as one offline file.
export default defineConfig(({ mode }) => {
  const film = mode === "film";
  return {
    plugins: film ? [viteSingleFile()] : [tailwindcss(), viteSingleFile()],
    build: {
      outDir: film ? "../out/film" : "../out/site",
      emptyOutDir: true,
      target: "es2022",
      assetsInlineLimit: 100_000_000,
      chunkSizeWarningLimit: 4000,
      rollupOptions: { input: film ? "film.html" : "fiam.html" },
    },
  };
});
