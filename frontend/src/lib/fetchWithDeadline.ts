import { throwIfAborted } from './videoFiles';

export async function fetchWithDeadline(
  input: RequestInfo | URL, init: RequestInit, signal: AbortSignal, timeoutMs = 30_000,
): Promise<Response> {
  throwIfAborted(signal);
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal.addEventListener('abort', cancel, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(input, { ...init, signal: controller.signal });
    // These endpoints return small acknowledgement/JSON bodies. Consume them
    // before detaching cancellation, so a stalled JSON body is also bounded.
    const body = [204, 205, 304].includes(response.status) ? null : await response.arrayBuffer();
    throwIfAborted(signal);
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  } catch (error) {
    throwIfAborted(signal);
    if (timedOut) throw new Error('The network request timed out. Please check your connection and retry.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', cancel);
  }
}
