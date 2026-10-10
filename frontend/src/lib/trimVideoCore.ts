import {
  ALL_FORMATS, BlobSource, BufferSource, BufferTarget, Conversion, Input,
  Mp4OutputFormat, Output,
} from 'mediabunny';
import { MAX_VIDEO_BYTES, TrimRange, validateTrimRange, validateVideoFile } from './videoFiles';

/** Runs only in the worker; the UI bundle never imports the media implementation. */
export async function createTrimmedVideo(file: File, range: TrimRange, onProgress: (value: number) => void) {
  validateVideoFile(file);
  validateTrimRange(range);
  const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
  let verification: Input | undefined;
  let conversion: Conversion | undefined;
  try {
    const video = await input.getPrimaryVideoTrack();
    if (!video) throw new Error('The selected file has no readable video track.');
    const sourceEnd = await video.computeDuration();
    const stats = await video.computePacketStats(120);
    const frameDuration = 1 / (stats.averagePacketRate || 30);
    const tolerance = Math.max(0.01, frameDuration + 0.005);
    // HTMLVideoElement.currentTime uses the movie clock, not time relative to
    // the first video packet. Phone tracks can start after the audio/movie.
    if (range.end > sourceEnd + tolerance) {
      throw new Error('The selected range extends beyond the readable video.');
    }
    const audio = await input.getPrimaryAudioTrack();
    const target = new BufferTarget();
    target.on('write', ({ end }) => {
      if (end > MAX_VIDEO_BYTES) throw new Error('The trimmed video exceeds the 150 MB upload limit.');
    });
    const output = new Output({ format: new Mp4OutputFormat({ fastStart: 'in-memory' }), target });
    // MP4 supports negative decode/presentation timestamps via edit lists.
    // Retain compressed reference packets needed to decode the first selected
    // frame, without re-encoding the recording's images or changing cadence.
    conversion = await Conversion.init({
      input, output, tracks: 'primary',
      trim: { start: range.start, end: range.end },
      copy: { mode: 'forced', shiftTolerance: 0, boundaryPolicy: 'expand' },
      showWarnings: false,
    });
    if (!conversion.isValid || !conversion.utilizedTracks.includes(video) ||
        (audio && !conversion.utilizedTracks.includes(audio))) {
      throw new Error('This recording cannot be trimmed losslessly into a compatible MP4 on this device.');
    }
    conversion.onProgress = (progress) => onProgress(Math.min(0.99, progress));
    await conversion.execute();
    const buffer = target.buffer;
    if (!buffer?.byteLength || buffer.byteLength > MAX_VIDEO_BYTES) {
      throw new Error('The trimmed video is empty or too large.');
    }
    verification = new Input({ formats: ALL_FORMATS, source: new BufferSource(buffer) });
    const resultVideo = await verification.getPrimaryVideoTrack();
    if (!resultVideo || await resultVideo.getCodec() !== await video.getCodec()) {
      throw new Error('The video trimmer did not preserve the recorded video codec.');
    }
    const duration = await resultVideo.computeDuration();
    if (Math.abs(duration - (range.end - range.start)) > tolerance ||
        await resultVideo.getFirstTimestamp() > tolerance ||
        await resultVideo.getDisplayWidth() !== await video.getDisplayWidth() ||
        await resultVideo.getDisplayHeight() !== await video.getDisplayHeight()) {
      throw new Error('A lossless cut cannot match this selection accurately. You can use server trimming or choose a different range.');
    }
    return { buffer, duration };
  } catch (error) {
    if (conversion && conversion.state !== 'done') await conversion.cancel().catch(() => {});
    throw error;
  } finally {
    verification?.dispose();
    input.dispose();
  }
}
