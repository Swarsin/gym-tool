export const MAX_VIDEO_BYTES = 150 * 1024 * 1024;
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'webm', 'm4v', 'avi'];

export interface TrimRange {
  start: number;
  end: number;
  sourceDuration: number;
}

export function validateVideoFile(file: File) {
  const extension = file.name.split('.').pop()?.toLowerCase() || '';
  if (!VIDEO_EXTENSIONS.includes(extension) && !file.type.startsWith('video/')) {
    throw new Error('Please select a video file (MP4, MOV, or WEBM).');
  }
  if (!file.size) throw new Error('The selected video is empty.');
  if (file.size > MAX_VIDEO_BYTES) {
    throw new Error(`Video is ${(file.size / 1024 / 1024).toFixed(1)} MB. Maximum upload size is 150 MB.`);
  }
}

export function validateTrimRange(range: TrimRange) {
  const { start, end, sourceDuration } = range;
  if (![start, end, sourceDuration].every(Number.isFinite) || sourceDuration <= 0 ||
      start < 0 || end > sourceDuration + 0.001 || end - start < 0.5 - 1e-7) {
    throw new Error('Select a valid video range of at least 0.5 seconds.');
  }
}

export function videoContentType(file: File): string {
  if (file.type) return file.type;
  const extension = file.name.split('.').pop()?.toLowerCase();
  return extension === 'mov' ? 'video/quicktime' : extension === 'webm' ? 'video/webm' : 'video/mp4';
}

export function abortError() {
  return new DOMException('Operation cancelled.', 'AbortError');
}

export function throwIfAborted(signal: AbortSignal) {
  if (signal.aborted) throw abortError();
}
