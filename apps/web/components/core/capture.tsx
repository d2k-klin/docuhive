"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Camera, FileUp, RotateCw, Trash2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { checkbox } from "@/lib/ui/control";
import { errorMessage } from "@/lib/i18n/errors";
import { prepareImage, reorder } from "@/lib/capture/images";
import { entries, flush, remove, save, type QueuedUpload, type UploadResult } from "../../public/capture-queue.js";

type Page = { id: string; file: File; preview?: string };
type Result = UploadResult & { title?: string; category?: string; state?: string };

export function Capture() {
  const [pages, setPages] = useState<Page[]>([]);
  const [combine, setCombine] = useState(true);
  const [queued, setQueued] = useState<QueuedUpload[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [owner, setOwner] = useState<number | null>(null);
  const [online, setOnline] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const camera = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const drag = useRef<number | null>(null);
  const urls = useRef(new Set<string>());
  const sending = useRef(false);
  const accepted = useCallback((result: UploadResult) => setResults(old => [...old, result]), []);
  const refresh = useCallback(async () => {
    const items = await entries();
    setQueued(items);
  }, []);
  const send = useCallback(async () => {
    if (sending.current || !navigator.onLine) return;
    sending.current = true;
    try {
      await flush(setMessage, accepted);
      await refresh();
      setMessage("");
    } catch {
      setError("Your queued files are kept on this device. Reconnect and try again.");
    } finally { sending.current = false; }
  }, [accepted, refresh]);

  useEffect(() => {
    // Device state is read after mount: the server render has neither storage nor network state.
    void Promise.resolve().then(() => {
      const saved = Number(localStorage.getItem("capture-owner"));
      if (saved) setOwner(saved);
      setOnline(navigator.onLine);
    });
    void fetch("/api/auth/me", { cache: "no-store" }).then(async response => {
      if (!response.ok) { setError("Sign in to send your captures. Queued files stay on this device."); setOwner(null); return; }
      const user = await response.json();
      localStorage.setItem("capture-owner", String(user.id));
      setOwner(user.id);
      void send();
    }).catch(() => {});
    void Promise.resolve()
      .then(refresh)
      .catch(() => setError("This browser cannot save captures. Keep your original files and enable site storage."));
    if ("serviceWorker" in navigator && window.isSecureContext) {
      void navigator.serviceWorker.register("/sw.js", { type: "module", updateViaCache: "none" })
        .catch(() => setError("Offline reopening is unavailable. Keep this page open until your upload finishes."));
    }
    const changed = () => { setOnline(navigator.onLine); if (navigator.onLine) void send(); };
    window.addEventListener("online", changed);
    window.addEventListener("offline", changed);
    const timer = setInterval(() => void send(), 15000);
    return () => { clearInterval(timer); window.removeEventListener("online", changed); window.removeEventListener("offline", changed); };
  }, [send, refresh]);
  useEffect(() => () => { for (const url of urls.current) URL.revokeObjectURL(url); }, []);
  useEffect(() => {
    const pending = results.filter(result => !result.state);
    if (!pending.length) return;
    let stopped = false;
    let count = 0;
    const timer = setInterval(async () => {
      count++;
      if (count > 40) { clearInterval(timer); return; }
      for (const result of pending) {
        try {
          const response = await fetch(`/api/documents/${encodeURIComponent(result.document_id)}`, { cache: "no-store" });
          if (!response.ok) continue;
          const doc = await response.json();
          if (!stopped && ["stored", "quarantined"].includes(doc.status)) setResults(old => old.map(item => item.document_id === result.document_id ? { ...item, state: doc.status, title: doc.title, category: doc.category } : item));
        } catch { /* The document link remains available while the server recovers. */ }
      }
    }, 3000);
    return () => { stopped = true; clearInterval(timer); };
  }, [results]);

  function page(file: File): Page {
    const preview = file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;
    if (preview) urls.current.add(preview);
    return { id: crypto.randomUUID(), file, preview };
  }
  async function add(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true); setError("");
    try {
      const added: Page[] = [];
      for (const file of Array.from(files)) {
        if (file.type.startsWith("image/")) added.push(page(await prepareImage(file)));
        else if (file.type === "application/pdf") added.push(page(file));
        else throw new Error();
      }
      setPages(old => [...old, ...added]);
    } catch { setError("This file could not be opened. Choose a JPEG, PNG or PDF, or try another photo."); }
    finally { setBusy(false); if (camera.current) camera.current.value = ""; if (picker.current) picker.current.value = ""; }
  }
  async function rotate(index: number) {
    setBusy(true);
    try {
      const next = page(await prepareImage(pages[index].file, 1));
      setPages(old => old.map((item, i) => i === index ? next : item));
    } catch { setError("The photo could not be rotated. Try choosing it again."); }
    finally { setBusy(false); }
  }
  async function upload() {
    if (!owner || !pages.length) return;
    setBusy(true); setError("");
    try {
      const groups = combine && pages.every(p => p.file.type.startsWith("image/")) ? [pages] : pages.map(p => [p]);
      for (const group of groups) await save({ id: crypto.randomUUID(), ownerId: owner, blobs: group.map(p => p.file), combine: group.length > 1, createdAt: Date.now(), attempts: 0, nextAttempt: 0 });
      // Clear previews only after IndexedDB has durably committed every selected file.
      setPages([]);
      await refresh();
      if ("storage" in navigator) void navigator.storage.persist?.();
      const registration = await navigator.serviceWorker?.getRegistration();
      if (registration && "sync" in registration) await (registration as ServiceWorkerRegistration & { sync: { register(tag: string): Promise<void> } }).sync.register("docuhive-uploads").catch(() => {});
      void send();
    } catch { setError("The capture could not be saved on this device. Keep this page open, free some storage and try again."); }
    finally { setBusy(false); }
  }
  const mine = queued.filter(item => item.ownerId === owner);
  return (
    <main className="mx-auto max-w-prose space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div><h1 className="text-xl font-semibold">Capture a document</h1><p className="text-sm text-text-muted">Photograph each page, put them in order, then send them to your archive.</p></div>
        <Link href="/" className="text-sm text-primary underline">Back to archive</Link>
      </header>
      <p className="text-xs text-text-muted">On your phone: open this page over HTTPS, then use Share → Add to Home Screen (iPhone) or the browser’s Install app menu (Android).</p>
      {error && <div role="alert" className="space-y-2 rounded-card border border-border bg-surface p-4"><p className="flex items-start gap-2 text-sm text-danger"><TriangleAlert aria-hidden="true" className="size-4 shrink-0" />{error}</p><Link href="/login?next=/capture" className="text-sm text-primary underline">Sign in</Link></div>}
      <input ref={camera} type="file" accept="image/*" capture="environment" multiple hidden aria-label="Camera photos" onChange={event => void add(event.target.files)} />
      <input ref={picker} type="file" accept="image/*,application/pdf" multiple hidden aria-label="Choose capture files" onChange={event => void add(event.target.files)} />
      <div className="flex flex-wrap gap-2">
        <Button size="lg" disabled={busy} onClick={() => camera.current?.click()}><Camera aria-hidden="true" />Take photo</Button>
        <Button size="lg" variant="secondary" disabled={busy} onClick={() => picker.current?.click()}><FileUp aria-hidden="true" />Choose files</Button>
      </div>
      {!pages.length && <p className="rounded-card border border-dashed border-border-strong p-6 text-sm text-text-muted">No pages selected. Take a photo or choose a file to begin.</p>}
      <ol className="space-y-3" aria-label="Pages in upload order">
        {pages.map((item, index) => <li key={item.id} draggable={!busy} onDragStart={() => { drag.current = index; }} onDragOver={event => event.preventDefault()} onDrop={() => { if (drag.current !== null) setPages(old => reorder(old, drag.current!, index)); drag.current = null; }} className="space-y-3 rounded-card border border-border bg-surface p-4">
          <div className="flex items-center gap-3">
            {item.preview && /* User-selected blob URLs need no image optimisation. */ <img src={item.preview} alt={`Page ${index + 1} preview`} className="h-24 w-16 rounded object-contain" />}
            <p className="min-w-0 break-all text-sm"><span className="font-medium">Page {index + 1}</span><br />{item.file.name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="lg" variant="secondary" aria-label={`Move page ${index + 1} earlier`} disabled={busy || index === 0} onClick={() => setPages(old => reorder(old, index, index - 1))}><ArrowUp aria-hidden="true" />Earlier</Button>
            <Button size="lg" variant="secondary" aria-label={`Move page ${index + 1} later`} disabled={busy || index === pages.length - 1} onClick={() => setPages(old => reorder(old, index, index + 1))}><ArrowDown aria-hidden="true" />Later</Button>
            {item.preview && <Button size="lg" variant="secondary" disabled={busy} aria-label={`Rotate page ${index + 1}`} onClick={() => void rotate(index)}><RotateCw aria-hidden="true" />Rotate</Button>}
            <Button size="lg" variant="ghost" disabled={busy} aria-label={`Remove page ${index + 1}`} onClick={() => setPages(old => old.filter((_, i) => i !== index))}><Trash2 aria-hidden="true" />Remove</Button>
          </div>
        </li>)}
      </ol>
      {pages.length > 1 && pages.every(p => p.file.type.startsWith("image/")) && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className={checkbox} checked={combine} onChange={event => setCombine(event.target.checked)} />Upload as one document</label>}
      {!!pages.length && <Button size="lg" className="w-full" disabled={busy || !owner} onClick={() => void upload()}>{busy ? "Preparing…" : online ? "Upload document" : "Save to upload when online"}</Button>}
      <section aria-label="Upload status" className="space-y-3" aria-live="polite">
        {message && <div role="status"><p>{message}</p><progress className="w-full" aria-label="Uploading document" /></div>}
        {mine.length > 0 && <p>{online ? "Queued" : "Offline — queued"}: {mine.length}. Files stay on this device until accepted. Reopen this page when online to finish.</p>}
        {queued.some(item => item.ownerId !== owner) && <p className="text-sm text-text-muted">This device also has captures for another account. Sign in to that account to send them.</p>}
        {mine.map(item => <article key={item.id} className="space-y-2 rounded-card border border-border bg-surface p-4"><p className="break-all text-sm">{item.blobs.map(file => file.name).join(", ")}</p>{item.error && <p role="alert" className="text-sm text-danger">{errorMessage(item.error)}</p>}<div className="flex gap-2"><Button variant="secondary" disabled={busy || !online} onClick={async () => { await save({ ...item, error: undefined, nextAttempt: 0, sendingUntil: 0 }); void send(); }}>Retry upload</Button><Button variant="ghost" disabled={busy} onClick={async () => { if (window.confirm("Remove this queued capture from this device? Keep your original photos before continuing.")) { await remove(item.id); await refresh(); } }}>Remove queued capture</Button></div></article>)}
        {results.map((result, index) => <article key={`${result.document_id}-${index}`} className="rounded-card border border-border bg-surface p-4"><p>{result.status === "duplicate" ? "Already in your archive" : result.state === "stored" ? result.title || "Document stored" : result.state === "quarantined" ? "This file needs attention. Open it to see the next step." : "Processing… Your file has been accepted."}</p>{result.category && <p className="text-sm text-text-muted">{result.category}</p>}<Link className="text-primary underline" href={`/documents/${encodeURIComponent(result.document_id)}`}>Open document</Link></article>)}
      </section>
      <p className="text-xs text-text-muted">Queued captures are saved in this browser on this device. Keep the original photos until the document is stored. Use a trusted device and remove its site data before passing it on.</p>
    </main>
  );
}
