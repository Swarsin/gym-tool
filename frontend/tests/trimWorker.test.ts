import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { trimVideo, LocalTrimError } from '../src/lib/trimVideo';

const originalWorker = globalThis.Worker;
class FakeWorker {
  static instances: FakeWorker[] = [];
  onmessage: ((event: any) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessageerror: (() => void) | null = null;
  terminated = 0;
  sent: any;
  constructor() { FakeWorker.instances.push(this); }
  postMessage(data: any) { this.sent = data; }
  terminate() { this.terminated++; }
  reply(data: any) { this.onmessage?.({ data }); }
}
const file = new File(['source'], 'clip.mov', { type: 'video/quicktime' });
const range = { start: 1, end: 3, sourceDuration: 5 };
beforeEach(() => { FakeWorker.instances = []; globalThis.Worker = FakeWorker as unknown as typeof Worker; });
afterEach(() => { globalThis.Worker = originalWorker; });

test('worker result becomes a correctly named/typed file; resources released on success', async () => {
  const signal = new AbortController();
  const progress: number[] = [];
  const promise = trimVideo(file, range, { signal: signal.signal, onProgress: value => progress.push(value) });
  const worker = FakeWorker.instances[0];
  worker.reply({ type: 'progress', progress: 1 });
  assert.equal(progress[0], .99); // 100% is not ready until finalization/verification.
  worker.reply({ type: 'complete', buffer: new Uint8Array([1, 2, 3]).buffer, duration: 2 });
  const result = await promise;
  assert.equal(result.file.name, 'clip.trimmed.mp4');
  assert.equal(result.file.type, 'video/mp4');
  assert.deepEqual(new Uint8Array(await result.file.arrayBuffer()), new Uint8Array([1, 2, 3]));
  assert.equal(worker.terminated, 1);
  signal.abort();
  assert.equal(worker.terminated, 1);
});

test('cancellation terminates real work, rejects as abort, and ignores late messages', async () => {
  const signal = new AbortController();
  const promise = trimVideo(file, range, { signal: signal.signal });
  const assertion = assert.rejects(promise, { name: 'AbortError' });
  const worker = FakeWorker.instances[0];
  signal.abort();
  await assertion;
  worker.reply({ type: 'complete', buffer: new ArrayBuffer(1), duration: 2 });
  assert.equal(worker.terminated, 1);
});

test('worker loading errors reject and release resources', async () => {
  const promise = trimVideo(file, range, { signal: new AbortController().signal });
  const assertion = assert.rejects(promise, LocalTrimError);
  FakeWorker.instances[0].onerror?.();
  await assertion;
  assert.equal(FakeWorker.instances[0].terminated, 1);
});

test('empty result is rejected instead of uploaded', async () => {
  const promise = trimVideo(file, range, { signal: new AbortController().signal });
  const assertion = assert.rejects(promise, /empty, invalid/);
  FakeWorker.instances[0].reply({ type: 'complete', buffer: new ArrayBuffer(0), duration: 2 });
  await assertion;
});

test('unsupported browser reports a local-trim error for explicit fallback', async () => {
  globalThis.Worker = undefined as unknown as typeof Worker;
  await assert.rejects(trimVideo(file, range, { signal: new AbortController().signal }), LocalTrimError);
});

test('stalled workers time out and are terminated', async (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const promise = trimVideo(file, range, { signal: new AbortController().signal });
  const assertion = assert.rejects(promise, /took too long/);
  context.mock.timers.tick(120_000);
  await assertion;
  assert.equal(FakeWorker.instances[0].terminated, 1);
});
