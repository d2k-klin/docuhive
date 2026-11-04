import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (
    path.startsWith("/api/") ||
    path === "/login" ||
    path.startsWith("/_next/") ||
    path === "/favicon.ico" ||
    [
      "/capture",
      "/manifest.webmanifest",
      "/sw.js",
      "/capture-queue.js",
      "/capture-192.png",
      "/capture-512.png",
    ].includes(path)
  )
    return NextResponse.next();
  if (process.env.NODE_ENV !== "production" && path.startsWith("/dev/"))
    return NextResponse.next();
  if (
    process.env.DOCUHIVE_ENV === "dev" &&
    process.env.DOCUHIVE_AUTH_DISABLED === "true"
  )
    return NextResponse.next();
  if (!request.cookies.has("dh_session")) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", path + request.nextUrl.search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

// API route handlers enforce auth/CSRF themselves; avoid Next proxy's body clone/buffer.
export const config = { matcher: ["/((?!api/|_next/static|_next/image).*)"] };
