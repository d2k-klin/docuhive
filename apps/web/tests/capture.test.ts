import { afterEach, describe, expect, it, vi } from "vitest";
import { prepareImage, reorder } from "../lib/capture/images";
afterEach(() => vi.unstubAllGlobals());

describe("capture images", () => {
  it("honours EXIF, downscales to 2400px and rotates without clipping", async () => {
    const close = vi.fn();
    const bitmap = vi.fn(async () => ({ width: 4000, height: 3000, close }));
    vi.stubGlobal("createImageBitmap", bitmap);
    const context = {
      fillRect: vi.fn(),
      translate: vi.fn(),
      rotate: vi.fn(),
      drawImage: vi.fn(),
    };
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => context,
      toBlob: (callback: (blob: Blob) => void) =>
        callback(new Blob(["image"], { type: "image/jpeg" })),
    };
    vi.stubGlobal("document", { createElement: () => canvas });
    const input = new File(["photo"], "letter.png", { type: "image/png" });
    const output = await prepareImage(input, 1);
    expect(bitmap).toHaveBeenCalledWith(input, {
      imageOrientation: "from-image",
    });
    expect(canvas.width).toBe(1800);
    expect(canvas.height).toBe(2400);
    expect(context.rotate).toHaveBeenCalledWith(Math.PI / 2);
    expect(output.type).toBe("image/jpeg");
    expect(close).toHaveBeenCalledOnce();
  });
  it("reorders pages without changing the input and ignores invalid moves", () => {
    const pages = [1, 2, 3];
    expect(reorder(pages, 2, 0)).toEqual([3, 1, 2]);
    expect(pages).toEqual([1, 2, 3]);
    expect(reorder(pages, -1, 0)).toEqual(pages);
  });
});
