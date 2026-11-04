import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "DocuHive capture",
    short_name: "DocuHive",
    start_url: "/capture",
    scope: "/",
    display: "standalone",
    background_color: "#f7f8fa",
    theme_color: "#2f5bea",
    icons: [
      {
        src: "/capture-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/capture-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
