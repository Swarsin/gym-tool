import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchWithDeadline } from '../src/lib/fetchWithDeadline';

test('cancellation stays connected until an acknowledgement body finishes', async context => {
  const upstream = new AbortController();
  let internal: AbortSignal;
  context.mock.method(globalThis, 'fetch', async (_url: any, init: any) => {
    internal = init.signal;
    return { status: 200, arrayBuffer: () => new Promise((_resolve, reject) => {
      internal.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')));
    }) } as Response;
  });
  const request = fetchWithDeadline('https://example.test/upload', {}, upstream.signal);
  const assertion = assert.rejects(request, { name: 'AbortError' });
  await new Promise(resolve => setImmediate(resolve));
  upstream.abort();
  await assertion;
  assert.equal(internal!.aborted, true);
});

test('a stalled JSON body times out instead of hanging the upload flow', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  context.mock.method(globalThis, 'fetch', async (_url: any, init: any) => ({
    status: 200, arrayBuffer: () => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')));
    }),
  } as Response));
  const request = fetchWithDeadline('https://example.test/analyze', {}, new AbortController().signal, 1000);
  const assertion = assert.rejects(request, /timed out/);
  await new Promise(resolve => setImmediate(resolve));
  context.mock.timers.tick(1000);
  await assertion;
});

test('204 storage acknowledgements remain valid empty responses', async context => {
  context.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 204 }));
  const response = await fetchWithDeadline('https://example.test/upload', {}, new AbortController().signal);
  assert.equal(response.status, 204);
  assert.equal(await response.text(), '');
});
