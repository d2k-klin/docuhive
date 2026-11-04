export type QueuedUpload = {
  id: string; ownerId: number; blobs: File[]; combine: boolean;
  createdAt: number; attempts: number; nextAttempt: number; sendingUntil?: number; error?: string;
};
export type UploadResult = { document_id: string; status: "staged" | "duplicate" };
export function entries(): Promise<QueuedUpload[]>;
export function save(entry: QueuedUpload): Promise<unknown>;
export function remove(id: string): Promise<unknown>;
export function flush(onProgress?: (message: string) => void, onResult?: (result: UploadResult) => void): Promise<void>;
