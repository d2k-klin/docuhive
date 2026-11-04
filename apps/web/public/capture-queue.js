// Shared by the capture page and its service worker. No document responses are cached.
const DB = "docuhive-uploads";
async function database() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore("uploads", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function transaction(mode, action) {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("uploads", mode);
      const request = action(tx.objectStore("uploads"));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () =>
        reject(tx.error || new Error("Queue write interrupted"));
    });
  } finally {
    db.close();
  }
}
export function entries() {
  return transaction("readonly", (store) => store.getAll());
}
export function save(entry) {
  return transaction("readwrite", (store) => store.put(entry));
}
export function remove(id) {
  return transaction("readwrite", (store) => store.delete(id));
}

// An IndexedDB write transaction claims a lease across tabs and service workers.
async function claim(id) {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("uploads", "readwrite");
      const store = tx.objectStore("uploads");
      let claimed = null;
      const request = store.get(id);
      request.onsuccess = () => {
        const entry = request.result;
        if (
          entry &&
          !entry.error &&
          (entry.sendingUntil || 0) < Date.now() &&
          entry.nextAttempt <= Date.now()
        ) {
          claimed = { ...entry, sendingUntil: Date.now() + 300000 };
          store.put(claimed);
        }
      };
      tx.oncomplete = () => resolve(claimed);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
export async function flush(onProgress = () => {}, onResult = () => {}) {
  const response = await fetch("/api/auth/me", { cache: "no-store" });
  if (!response.ok) return;
  const user = await response.json();
  for (const pending of await entries()) {
    if (pending.ownerId !== user.id) continue;
    const entry = await claim(pending.id);
    if (!entry) continue;
    try {
      const form = new FormData();
      for (const file of entry.blobs)
        form.append("files", file, file.name || "capture.jpg");
      const query = new URLSearchParams({
        combine: String(entry.combine),
        source: "mobile",
        expected_owner_id: String(entry.ownerId),
      });
      onProgress("Uploading…");
      const result = await fetch(`/api/upload?${query}`, {
        method: "POST",
        body: form,
        headers: { "X-DocuHive-CSRF": "1" },
        signal: AbortSignal.timeout(240000),
      });
      if (result.ok) {
        const body = await result.json();
        if (!body.document_id || !["staged", "duplicate"].includes(body.status))
          throw new Error("Invalid intake response");
        await remove(entry.id);
        onResult(body);
      } else {
        const terminal = [400, 413, 415, 422].includes(result.status);
        const error = terminal
          ? (await result.json()).error?.code || "unsupported_type"
          : undefined;
        await save({
          ...entry,
          sendingUntil: 0,
          attempts: entry.attempts + 1,
          nextAttempt:
            Date.now() +
            Math.min(3600000, 1000 * 2 ** Math.min(entry.attempts + 1, 12)),
          error,
        });
        if (result.status === 401 || result.status === 403) break;
      }
    } catch {
      await save({
        ...entry,
        sendingUntil: 0,
        attempts: entry.attempts + 1,
        nextAttempt:
          Date.now() +
          Math.min(3600000, 1000 * 2 ** Math.min(entry.attempts + 1, 12)),
      });
    }
  }
}
