import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VideoUploadController, type UploadDependencies, type VideoUploadRequest, type UploadState } from '../src/lib/videoUploadController';
import { MAX_VIDEO_BYTES, validateTrimRange, validateVideoFile, videoContentType } from '../src/lib/videoFiles';

const original = new File(['original-file-bytes'], 'recording.mov', { type: 'video/quicktime' });
const clip = new File(['selected-clip-bytes'], 'recording.trimmed.mp4', { type: 'video/mp4' });
const request: VideoUploadRequest = { file: original, range: { start: 10, end: 25, sourceDuration: 60 },
  exerciseName: 'Pull-Up / Chin-Up', userHeightCm: 178, userId: 'user', accessToken: 'token' };
const prepared = { file: clip, duration: 15, preparationMs: 123 };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function setup(overrides: Partial<UploadDependencies> = {}) {
  const uploads: VideoUploadRequest[] = [];
  const states: UploadState[] = [];
  const controller = new VideoUploadController({
    trim: async () => prepared,
    upload: async (value) => { uploads.push(value); return 12; },
    ...overrides,
  }, (state) => states.push(state));
  return { controller, uploads, states };
}

test('prepares before uploading; uploads new bytes and removes original trim offsets', async () => {
  const pending = deferred<typeof prepared>();
  const { controller, uploads } = setup({ trim: () => pending.promise });
  const running = controller.start(request);
  assert.equal(controller.state.phase, 'preparing');
  assert.equal(uploads.length, 0);
  pending.resolve(prepared);
  await running;
  assert.equal(uploads[0].file, clip);
  assert.equal(uploads[0].range, null);
  assert.equal(uploads[0].exerciseName, request.exerciseName);
  assert.equal(controller.state.logId, 12);
  assert.equal(controller.state.preparationMs, 123);
});

test('local failure never uploads original until explicit server fallback', async () => {
  const { controller, uploads } = setup({ trim: async () => { throw new Error('Unsupported codec'); } });
  await controller.start(request);
  assert.equal(controller.state.phase, 'fallback');
  assert.equal(uploads.length, 0);
  await controller.useServerTrim();
  assert.equal(uploads.length, 1);
  assert.equal(uploads[0].file, original);
  assert.deepEqual(uploads[0].range, request.range);
});

test('retry trims locally again rather than uploading original', async () => {
  let count = 0;
  const { controller, uploads } = setup({ trim: async () => { if (++count === 1) throw new Error('Worker load failed'); return prepared; } });
  await controller.start(request);
  await controller.retry();
  assert.equal(count, 2);
  assert.equal(uploads[0].file, clip);
  assert.equal(uploads[0].range, null);
});

test('cancelling during trimming aborts signal and ignores late completion', async () => {
  const pending = deferred<typeof prepared>();
  let signal: AbortSignal;
  const { controller, uploads } = setup({ trim: (_file, _range, options) => { signal = options.signal; return pending.promise; } });
  const running = controller.start(request);
  controller.cancel();
  assert.equal(signal!.aborted, true);
  pending.resolve(prepared);
  await running;
  assert.equal(controller.state.phase, 'idle');
  assert.equal(uploads.length, 0);
  await controller.useServerTrim();
  assert.equal(uploads.length, 0);
});

test('cancelled preparation rejection does not surface fallback', async () => {
  const pending = deferred<typeof prepared>();
  const { controller, uploads } = setup({ trim: () => pending.promise });
  const running = controller.start(request);
  controller.cancel();
  pending.reject(new Error('Worker stopped'));
  await running;
  assert.equal(controller.state.phase, 'idle');
  assert.equal(uploads.length, 0);
});

test('late old completion cannot replace a new operation', async () => {
  const pending = deferred<typeof prepared>();
  let count = 0;
  const { controller, uploads } = setup({ trim: () => ++count === 1 ? pending.promise : Promise.resolve(prepared) });
  const old = controller.start(request);
  controller.cancel();
  await controller.start({ ...request, exerciseName: 'Barbell Row' });
  pending.resolve(prepared);
  await old;
  assert.equal(uploads.length, 1);
  assert.equal(uploads[0].exerciseName, 'Barbell Row');
  assert.equal(controller.state.phase, 'processing');
});

test('duplicate confirms do not start a second worker or upload', async () => {
  const pending = deferred<typeof prepared>();
  let count = 0;
  const { controller, uploads } = setup({ trim: () => { count++; return pending.promise; } });
  const running = controller.start(request);
  await controller.start(request);
  assert.equal(count, 1);
  pending.resolve(prepared);
  await running;
  assert.equal(uploads.length, 1);
});

test('cancel during upload suppresses late analysis ID and aborts upload signal', async () => {
  const pending = deferred<number>();
  let signal: AbortSignal;
  const { controller } = setup({ upload: (_request, value) => { signal = value; return pending.promise; } });
  const running = controller.start({ ...request, range: null });
  assert.equal(controller.state.phase, 'uploading');
  controller.cancel();
  assert.equal(signal!.aborted, true);
  pending.resolve(12);
  await running;
  assert.equal(controller.state.phase, 'idle');
  assert.equal(controller.state.logId, undefined);
});

test('entire video and full-range selections bypass unnecessary conversion', async () => {
  let count = 0;
  const { controller, uploads } = setup({ trim: async () => { count++; return prepared; } });
  await controller.start({ ...request, range: null });
  await controller.start({ ...request, range: { start: 0, end: 60, sourceDuration: 60 } });
  assert.equal(count, 0);
  assert.equal(uploads[0].file, original);
  assert.equal(uploads[1].range, null);
});

test('malformed job IDs become recoverable errors', async () => {
  const { controller } = setup({ upload: async () => undefined as unknown as number });
  await controller.start(request);
  assert.equal(controller.state.phase, 'failed');
  assert.match(controller.state.error!, /invalid job ID/);
});

test('invalid or oversized inputs do not enter preparation or upload', async () => {
  const { controller, uploads } = setup();
  await controller.start({ ...request, range: { start: 4, end: 3, sourceDuration: 60 } });
  assert.equal(controller.state.phase, 'failed');
  assert.equal(uploads.length, 0);
  assert.throws(() => validateVideoFile({ name: 'clip.mp4', type: 'video/mp4', size: MAX_VIDEO_BYTES + 1 } as File));
  assert.doesNotThrow(() => validateVideoFile({ name: 'clip.mp4', type: 'video/mp4', size: MAX_VIDEO_BYTES } as File));
  for (const range of [{ start: NaN, end: 4, sourceDuration: 5 }, { start: 0, end: Infinity, sourceDuration: 5 },
    { start: -1, end: 4, sourceDuration: 5 }, { start: 0, end: 6, sourceDuration: 5 }]) {
    assert.throws(() => validateTrimRange(range));
  }
});

test('empty picker MIME is inferred from container extension', () => {
  assert.equal(videoContentType(new File(['x'], 'clip.mov')), 'video/quicktime');
  assert.equal(videoContentType(new File(['x'], 'clip.webm')), 'video/webm');
});
