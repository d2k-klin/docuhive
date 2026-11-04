// Only the configured backend receives credentials; redirects are returned to the browser.
const requestHeaders = [
  "cookie",
  "content-type",
  "range",
  "if-none-match",
  "x-docuhive-csrf",
  "authorization",
];
const responseHeaders = [
  "content-type",
  "content-length",
  "content-disposition",
  "etag",
  "accept-ranges",
  "content-range",
  "cache-control",
  "retry-after",
  "location",
];

export async function proxy(
  request: Request,
  path: string[],
  backend: string,
): Promise<Response> {
  if (
    path.some(
      (segment) =>
        segment === "." || segment === ".." || /[\\/\x00]/.test(segment),
    )
  ) {
    return Response.json(
      {
        error: {
          code: "invalid_path",
          message: "Invalid request path",
          details: {},
        },
      },
      { status: 400 },
    );
  }
  const incoming = new URL(request.url);
  const mutates = !["GET", "HEAD", "OPTIONS"].includes(request.method);
  if (mutates && !request.headers.has("authorization")) {
    const origin = request.headers.get("origin");
    const host = request.headers.get("host") || incoming.host;
    const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",")[0].trim();
    const protocol = forwardedProtocol === "https" || forwardedProtocol === "http"
      ? `${forwardedProtocol}:` : incoming.protocol;
    const publicOrigin = new URL(process.env.DOCUHIVE_PUBLIC_URL || `${protocol}//${host}`).origin;
    if (
      (origin && origin !== publicOrigin) ||
      request.headers.get("x-docuhive-csrf") !== "1"
    ) {
      return Response.json(
        {
          error: {
            code: "csrf_required",
            message: "Reload and try again.",
            details: {},
          },
        },
        { status: 403 },
      );
    }
  }
  const headers = new Headers();
  for (const name of requestHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const upstream = new URL(
    `/api/${path.map(encodeURIComponent).join("/")}`,
    backend,
  );
  upstream.search = incoming.search;
  try {
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    };
    if (mutates && request.body) {
      init.body = request.body;
      init.duplex = "half";
    }
    const response = await fetch(upstream, init);
    const outgoing = new Headers();
    for (const name of responseHeaders) {
      const value = response.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    for (const cookie of response.headers.getSetCookie())
      outgoing.append("set-cookie", cookie);
    if (response.headers.has("content-encoding"))
      outgoing.delete("content-length");
    if (!outgoing.has("cache-control"))
      outgoing.set("cache-control", "private, no-store");
    if (response.headers.get("content-type")?.startsWith("text/event-stream")) {
      outgoing.set("cache-control", "no-cache");
      outgoing.set("x-accel-buffering", "no");
    }
    return new Response(response.body, {
      status: response.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "api_unavailable",
          message: "The server is unavailable. Try again shortly.",
          details: {},
        },
      },
      { status: 502 },
    );
  }
}
