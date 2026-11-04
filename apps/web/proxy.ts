import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (
    path.startsWith("/api/") ||
    path === "/login" ||
    path.startsWith("/_next/") ||
    path === "/favicon.ico" ||
    // Static capture assets without user data; a redirected service worker never installs.
    path === "/sw.js" ||
    path === "/capture-queue.js" ||
    path === "/manifest.webmanifest"
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

export const config = { matcher: ["/((?!_next/static|_next/image).*)"] };
