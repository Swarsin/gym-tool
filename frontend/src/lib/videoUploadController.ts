import type { TrimmedVideo } from './trimVideo';
import { TrimRange, throwIfAborted, validateTrimRange, validateVideoFile } from './videoFiles';

export interface VideoUploadRequest {
  file: File;
  range: TrimRange | null;
  exerciseName: string;
  userHeightCm: number | null;
  userId?: string;
  accessToken: string;
}

export interface UploadState {
  phase: 'idle' | 'preparing' | 'fallback' | 'uploading' | 'processing' | 'failed';
  progress: number;
  selectedDuration?: number;
  uploadBytes?: number;
  preparationMs?: number;
  error?: string;
  logId?: number;
}

export interface UploadDependencies {
  trim: (file: File, range: TrimRange, options: { signal: AbortSignal; onProgress: (value: number) => void }) => Promise<TrimmedVideo>;
  upload: (request: VideoUploadRequest, signal: AbortSignal) => Promise<number>;
}

export const INITIAL_UPLOAD_STATE: UploadState = { phase: 'idle', progress: 0 };

/** Owns the operation independently of the upload form's mount/unmount lifecycle. */
export class VideoUploadController {
  state: UploadState = INITIAL_UPLOAD_STATE;
  private operation: { controller: AbortController; request: VideoUploadRequest } | null = null;

  constructor(private dependencies: UploadDependencies, private onChange: (state: UploadState) => void) {}

  private update(state: UploadState) {
    this.state = state;
    this.onChange(state);
  }

  cancel(notify = true) {
    this.operation?.controller.abort();
    this.operation = null;
    this.state = INITIAL_UPLOAD_STATE;
    if (notify) this.onChange(this.state);
  }

  retry() {
    if (this.state.phase === 'fallback' && this.operation) return this.start(this.operation.request);
  }

  useServerTrim() {
    if (this.state.phase === 'fallback' && this.operation) return this.start(this.operation.request, true);
  }

  async start(request: VideoUploadRequest, serverTrim = false) {
    if (this.state.phase === 'preparing' || this.state.phase === 'uploading') return;
    this.cancel(false);
    const operation = { controller: new AbortController(), request };
    this.operation = operation;
    const signal = operation.controller.signal;
    const isCurrent = () => this.operation === operation && !signal.aborted;
    try {
      if (!request.accessToken) throw new Error('Please sign in before uploading a video.');
      validateVideoFile(request.file);
      if (request.range) validateTrimRange(request.range);
      let uploadRequest = request;
      let preparationMs = 0;
      const entireRange = request.range && request.range.start === 0 &&
        Math.abs(request.range.end - request.range.sourceDuration) < 0.001;
      if (request.range && !entireRange && !serverTrim) {
        this.update({ phase: 'preparing', progress: 0, selectedDuration: request.range.end - request.range.start });
        let prepared: TrimmedVideo;
        try {
          prepared = await this.dependencies.trim(request.file, request.range, {
            signal,
            onProgress: (progress) => {
              if (isCurrent()) this.update({ ...this.state, progress });
            },
          });
        } catch (error) {
          if (!isCurrent()) return;
          this.update({ ...this.state, phase: 'fallback', error: error instanceof Error ? error.message : 'On-device trimming failed.' });
          return; // No storage calls until the user explicitly chooses a fallback.
        }
        if (!isCurrent()) return;
        validateVideoFile(prepared.file);
        uploadRequest = { ...request, file: prepared.file, range: null };
        preparationMs = prepared.preparationMs;
      } else if (entireRange) {
        uploadRequest = { ...request, range: null };
      }
      if (!isCurrent()) return;
      throwIfAborted(signal);
      this.update({ phase: 'uploading', progress: 1, uploadBytes: uploadRequest.file.size,
        selectedDuration: request.range ? request.range.end - request.range.start : undefined, preparationMs });
      const logId = await this.dependencies.upload(uploadRequest, signal);
      if (!isCurrent()) return;
      if (!Number.isSafeInteger(logId) || logId <= 0) throw new Error('The analysis server returned an invalid job ID.');
      this.operation = null;
      this.update({ ...this.state, phase: 'processing', logId });
    } catch (error) {
      if (!isCurrent()) return;
      this.operation = null;
      this.update({ ...this.state, phase: 'failed', error: error instanceof Error ? error.message : 'Video upload failed.' });
    }
  }
}
