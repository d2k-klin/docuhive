import { afterEach, describe, expect, it, vi } from "vitest";
import { proxy } from "../lib/proxy";

afterEach(() => vi.unstubAllGlobals());

describe("streaming BFF", () => {
  it("checks the browser host when Next normalizes its internal URL", async () => {
    const upstream = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", upstream);
    const response = await proxy(new Request("http://localhost:3100/api/auth/login", {
      method: "POST", headers: { host: "127.0.0.1:3100", origin: "http://127.0.0.1:3100", "x-docuhive-csrf": "1" },
    }), ["auth", "login"], "http://backend:8000");
    expect(response.status).toBe(204);
    expect(upstream).toHaveBeenCalledOnce();
  });
  it("rejects cross-site mutations and unsafe paths before sending credentials", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const response = await proxy(
      new Request("https://docs.invalid/api/auth/logout", {
        method: "POST",
        headers: { origin: "https://evil.invalid", "x-docuhive-csrf": "1" },
      }),
      ["auth", "logout"],
      "http://backend:8000",
    );
    expect(response.status).toBe(403);
    expect(
      (
        await proxy(
          new Request("https://docs.invalid/api/x"),
          [".."],
          "http://backend:8000",
        )
      ).status,
    ).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("passes upload bodies as streams and preserves cookies and query parameters", async () => {
    const upstream = vi.fn(
      async () =>
        new Response(null, {
          status: 204,
          headers: { "set-cookie": "dh_session=new; HttpOnly" },
        }),
    );
    vi.stubGlobal("fetch", upstream);
    const request = new Request(
      "https://docs.invalid/api/upload?combine=true",
      {
        method: "POST",
        body: new Uint8Array(50 * 1024 * 1024),
        headers: { "x-docuhive-csrf": "1", cookie: "dh_session=old" },
      },
    );
    const response = await proxy(request, ["upload"], "http://backend:8000");
    const [url, init] = upstream.mock.calls[0] as unknown as [
      URL,
      RequestInit & { duplex: string },
    ];
    expect(url.toString()).toBe("http://backend:8000/api/upload?combine=true");
    expect(init.body).toBe(request.body);
    expect(init.duplex).toBe("half");
    expect(response.status).toBe(204);
    expect(response.headers.get("set-cookie")).toContain("dh_session=new");
  });

  it("delivers SSE chunks before upstream completion", async () => {
    let stream!: ReadableStreamDefaultController<Uint8Array>;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            new ReadableStream({
              start(controller) {
                stream = controller;
              },
            }),
            {
              headers: { "content-type": "text/event-stream" },
            },
          ),
      ),
    );
    const response = await proxy(
      new Request("https://docs.invalid/api/system/sse-test"),
      ["system", "sse-test"],
      "http://backend:8000",
    );
    const reader = response.body!.getReader();
    stream.enqueue(new TextEncoder().encode("data: first\n\n"));
    expect(new TextDecoder().decode((await reader.read()).value)).toContain(
      "first",
    );
    stream.enqueue(new TextEncoder().encode("data: second\n\n"));
    expect(new TextDecoder().decode((await reader.read()).value)).toContain(
      "second",
    );
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    stream.close();
  });
});
