import { throwIfAborted } from './videoFiles';

/** Read the movie clock even when the browser cannot play its video codec. */
export async function readVideoDuration(file: File, signal: AbortSignal): Promise<number> {
  const { Input, ALL_FORMATS, BlobSource } = await import('mediabunny');
  throwIfAborted(signal);
  const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
  const cancel = () => input.dispose();
  signal.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(cancel, 30_000);
  try {
    const video = await input.getPrimaryVideoTrack();
    if (!video) throw new Error('The file has no readable video track.');
    const duration = await input.getDurationFromMetadata() ?? await input.computeDuration();
    throwIfAborted(signal);
    if (!Number.isFinite(duration) || duration <= 0) throw new Error('The video duration could not be read.');
    return duration;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', cancel);
    input.dispose();
  }
}
