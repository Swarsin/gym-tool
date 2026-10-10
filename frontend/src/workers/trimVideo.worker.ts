import { createTrimmedVideo } from '../lib/trimVideoCore';
import type { TrimRange } from '../lib/videoFiles';

self.onmessage = async ({ data }: MessageEvent<{ file: File; range: TrimRange }>) => {
  try {
    const result = await createTrimmedVideo(data.file, data.range, (progress) => {
      self.postMessage({ type: 'progress', progress });
    });
    self.postMessage({ type: 'complete', ...result }, { transfer: [result.buffer] });
  } catch (error) {
    self.postMessage({ type: 'error', message: error instanceof Error ? error.message : 'On-device trimming failed.' });
  }
};
