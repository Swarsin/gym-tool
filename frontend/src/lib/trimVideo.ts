import { abortError, MAX_VIDEO_BYTES, TrimRange, validateTrimRange, validateVideoFile } from './videoFiles';

export interface TrimmedVideo {
  file: File;
  duration: number;
  preparationMs: number;
}

export type TrimWorkerReply =
  | { type: 'progress'; progress: number }
  | { type: 'complete'; buffer: ArrayBuffer; duration: number }
  | { type: 'error'; message: string };

export class LocalTrimError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'LocalTrimError';
  }
}

/** A dedicated, lazy-loaded worker owns all codecs and buffers for one clip. */
export async function trimVideo(
  file: File,
  range: TrimRange,
  { signal, onProgress }: { signal: AbortSignal; onProgress?: (progress: number) => void },
): Promise<TrimmedVideo> {
  validateVideoFile(file);
  validateTrimRange(range);
  if (signal.aborted) throw abortError();
  if (typeof Worker === 'undefined') {
    throw new LocalTrimError('This browser cannot run on-device video trimming.');
  }
  const started = performance.now();
  return new Promise((resolve, reject) => {
    let worker: Worker;
    try {
      worker = new Worker(new URL('../workers/trimVideo.worker.ts', import.meta.url), { type: 'module' });
    } catch {
      reject(new LocalTrimError('The video trimming worker could not be started.'));
      return;
    }
    let settled = false;
    const cleanup = () => {
      clearTimeout(timeout);
      signal.removeEventListener('abort', cancel);
      worker.terminate();
    };
    const fail = (error: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    };
    const cancel = () => fail(abortError());
    const timeout = setTimeout(() => fail(new LocalTrimError(
      'On-device trimming took too long. You can retry or use server trimming.',
    )), 120_000);
    signal.addEventListener('abort', cancel, { once: true });
    worker.onerror = () => fail(new LocalTrimError('The browser could not load or run the video trimmer.'));
    worker.onmessageerror = () => fail(new LocalTrimError('The video trimmer returned an unreadable result.'));
    worker.onmessage = ({ data }: MessageEvent<TrimWorkerReply>) => {
      if (settled) return;
      if (data.type === 'progress') {
        if (Number.isFinite(data.progress)) onProgress?.(Math.min(0.99, Math.max(0, data.progress)));
      } else if (data.type === 'error') {
        fail(new LocalTrimError(data.message));
      } else if (data.type === 'complete') {
        if (!(data.buffer instanceof ArrayBuffer) || !data.buffer.byteLength ||
            data.buffer.byteLength > MAX_VIDEO_BYTES || !Number.isFinite(data.duration) || data.duration <= 0) {
          fail(new LocalTrimError('The trimmed clip was empty, invalid, or larger than 150 MB.'));
          return;
        }
        const name = `${file.name.replace(/\.[^.]+$/, '')}.trimmed.mp4`;
        const trimmedFile = new File([data.buffer], name, { type: 'video/mp4' });
        settled = true;
        cleanup();
        onProgress?.(1);
        resolve({ file: trimmedFile, duration: data.duration, preparationMs: performance.now() - started });
      }
    };
    try {
      worker.postMessage({ file, range });
      if (signal.aborted) cancel();
    } catch {
      fail(new LocalTrimError('The selected video could not be sent to the on-device trimmer.'));
    }
  });
}
