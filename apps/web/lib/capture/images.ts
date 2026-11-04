export async function prepareImage(file: File, turns = 0): Promise<File> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    const scale = Math.min(1, 2400 / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = turns % 2 ? height : width;
    canvas.height = turns % 2 ? width : height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Image processing unavailable");
    context.fillStyle = "white";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.translate(canvas.width / 2, canvas.height / 2);
    context.rotate(turns * Math.PI / 2);
    context.drawImage(bitmap, -width / 2, -height / 2, width, height);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("Image conversion failed")), "image/jpeg", 0.85),
    );
    return new File([blob], `${file.name.replace(/\.[^.]+$/, "")}.jpg`, { type: "image/jpeg" });
  } finally { bitmap.close(); }
}
export function reorder<T>(items: T[], from: number, to: number): T[] {
  const result = [...items];
  if (from < 0 || to < 0 || from >= result.length || to >= result.length) return result;
  result.splice(to, 0, result.splice(from, 1)[0]);
  return result;
}
