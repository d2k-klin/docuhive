import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "Permissions-Policy", value: "camera=(self)" },
          // ponytail: no COEP; nothing needs cross-origin isolation, and require-corp would add risk for no gain.
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
        ],
      },
      {
        // Everything except a document's file, which the preview frames (below).
        source: "/:path((?!api/documents/[0-9A-Z]{26}/file$).*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}; style-src 'self' 'unsafe-inline'; frame-src 'self'; img-src 'self' data: blob:; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`,
          },
        ],
      },
      {
        // The document preview frames the archive PDF from our own origin; nothing else may.
        source: "/api/documents/:id/file",
        headers: [
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; object-src 'self'; frame-ancestors 'self'",
          },
        ],
      },
    ];
  },
};
export default config;
