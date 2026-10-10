import { test, expect, type Page } from '@playwright/test';
import { readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

async function selectRange(page: Page) {
  await page.goto('/tests/fixtures/upload.html');
  await page.locator('#video-upload').setInputFiles('tests/fixtures/source.mp4');
  await expect(page.getByRole('button', { name: 'Analyze Selected Range' })).toBeEnabled();
  await page.getByRole('button', { name: '+0.5s', exact: true }).first().click();
  await page.getByRole('button', { name: '-0.5s', exact: true }).last().click();
}

async function mockUploads(page: Page, provider: 'r2' | 'supabase' = 'r2') {
  const bodies: Buffer[] = [];
  const analyses: any[] = [];
  const presigns: any[] = [];
  const key = randomUUID();
  await page.route('**/test-api/api/v1/storage/upload-url', async route => {
    presigns.push(route.request().postDataJSON());
    await route.fulfill({ json: provider === 'r2'
      ? { provider, upload_url: `http://127.0.0.1:4178/test-upload?key=${key}`, public_url: 'http://127.0.0.1:4177/uploaded.mp4' }
      : { provider } });
  });
  await page.route('**/test-storage/storage/v1/object/workout-videos/**', async route => {
    bodies.push(route.request().postDataBuffer()!);
    await route.fulfill({ json: { Id: 'test-object', Key: 'workout-videos/test.mp4' } });
  });
  await page.route('**/test-api/api/v1/analyze', async route => {
    if (provider === 'r2') {
      const response = await fetch(`http://127.0.0.1:4178/capture?key=${key}`);
      bodies.push(Buffer.from(await response.arrayBuffer()));
    }
    analyses.push(route.request().postDataJSON());
    await route.fulfill({ status: 202, json: { log_id: 12 } });
  });
  return { bodies, analyses, presigns };
}

test('actual worker trim uploads selected MP4 bytes with null backend trim offsets', async ({ page }, info) => {
  const storage = await mockUploads(page);
  await selectRange(page);
  await page.getByRole('button', { name: 'Analyze Selected Range' }).click();
  await expect(page.getByTestId('phase')).toHaveText('processing');
  expect(storage.bodies).toHaveLength(1);
  expect(storage.presigns[0]).toEqual({ filename: 'source.trimmed.mp4', content_type: 'video/mp4' });
  expect(storage.analyses[0].trim_start_s).toBeNull();
  expect(storage.analyses[0].trim_end_s).toBeNull();
  expect(storage.bodies[0].equals(await readFile('tests/fixtures/source.mp4'))).toBe(false);
  // Parse the uploaded bytes in the browser, not only the UI's reported range.
  const properties = await page.evaluate(async bytes => {
    const { Input, ALL_FORMATS, BufferSource, VideoSampleSink } = await import('/node_modules/mediabunny/dist/modules/src/index.js');
    const input = new Input({ formats: ALL_FORMATS, source: new BufferSource(new Uint8Array(bytes)) });
    const video = await input.getPrimaryVideoTrack();
    let first: number | null = null;
    if (await video!.canDecode()) {
      const sample = (await new VideoSampleSink(video!).getSample(0))!;
      first = sample.timestamp;
      sample.close();
    }
    const properties = { duration: await video!.computeDuration(), codec: await video!.getCodec(),
      width: await video!.getDisplayWidth(), height: await video!.getDisplayHeight(),
      first, audio: !!await input.getPrimaryAudioTrack() };
    input.dispose();
    return properties;
  }, Array.from(storage.bodies[0]));
  expect(properties.duration).toBeCloseTo(5, 1);
  expect(properties).toMatchObject({ codec: 'avc', width: 160, height: 120, audio: true });
  if (properties.first !== null) expect(Math.abs(properties.first)).toBeLessThan(.034);
  await info.attach('uploaded-video', { body: storage.bodies[0], contentType: 'video/mp4' });
});

test('storage-provider fallback still uploads the prepared file', async ({ page }) => {
  const storage = await mockUploads(page, 'supabase');
  await selectRange(page);
  await page.getByRole('button', { name: 'Analyze Selected Range' }).click();
  await expect(page.getByTestId('phase')).toHaveText('processing');
  expect(storage.bodies).toHaveLength(1);
  expect(storage.bodies[0].toString('latin1')).toContain('source.trimmed.mp4');
  expect(storage.bodies[0].toString('latin1')).toContain('video/mp4');
  expect(storage.analyses[0].trim_start_s).toBeNull();
});

test('worker failure requires explicit server fallback and preserves original bytes/range', async ({ page }) => {
  await page.addInitScript(() => { window.Worker = class { constructor() { throw new Error('Unavailable'); } } as any; });
  const storage = await mockUploads(page);
  await selectRange(page);
  await page.getByRole('button', { name: 'Analyze Selected Range' }).click();
  await expect(page.getByText('On-device trimming unavailable')).toBeVisible();
  expect(storage.presigns).toHaveLength(0);
  expect(storage.bodies).toHaveLength(0);
  await page.getByRole('button', { name: 'Upload original & trim on server' }).click();
  await expect(page.getByTestId('phase')).toHaveText('processing');
  expect(storage.bodies[0].equals(await readFile('tests/fixtures/source.mp4'))).toBe(true);
  expect(storage.analyses[0]).toMatchObject({ trim_start_s: .5, trim_end_s: 5.5 });
});

test('cancelling failed preparation uploads nothing and returns to selection', async ({ page }) => {
  await page.addInitScript(() => { window.Worker = undefined as any; });
  const storage = await mockUploads(page);
  await selectRange(page);
  await page.getByRole('button', { name: 'Analyze Selected Range' }).click();
  await expect(page.getByTestId('phase')).toHaveText('fallback');
  await page.getByRole('button', { name: 'Cancel and return home' }).click();
  await expect(page.getByTestId('phase')).toHaveText('idle');
  expect(storage.bodies).toHaveLength(0);
  expect(storage.analyses).toHaveLength(0);
});

test('aborting an R2 upload does not start storage fallback or analysis', async ({ page }) => {
  const storage = await mockUploads(page);
  let reachedUpload = false;
  await page.route('**/test-upload?*', async route => {
    reachedUpload = true;
    await new Promise(resolve => setTimeout(resolve, 500));
    await route.fulfill({ status: 200, body: '' }).catch(() => {});
  });
  await page.goto('/tests/fixtures/upload.html');
  await page.locator('#video-upload').setInputFiles('tests/fixtures/source.mp4');
  await page.getByRole('button', { name: 'Analyze Entire Video' }).click();
  await expect.poll(() => reachedUpload).toBe(true);
  await page.getByRole('button', { name: 'Cancel upload' }).click();
  await expect(page.getByTestId('phase')).toHaveText('idle');
  await page.waitForTimeout(600);
  expect(storage.bodies).toHaveLength(0);
  expect(storage.analyses).toHaveLength(0);
});

for (const fixture of ['source.mp4', 'source.webm', 'variable.mp4', 'rotated.mov', 'hevc.mov']) {
  test(`real media: ${fixture} keeps duration, cadence, orientation and cut content`, async ({ page }, info) => {
    await page.goto('/tests/fixtures/upload.html');
    const result = await page.evaluate(async name => {
      const { trimVideo } = await import('/src/lib/trimVideo.ts');
      const { Input, ALL_FORMATS, BlobSource, VideoSampleSink, EncodedPacketSink } = await import('/node_modules/mediabunny/dist/modules/src/index.js');
      const file = new File([await (await fetch(`/tests/fixtures/${name}`)).blob()], name);
      const range = { start: 1.1, end: 4.25, sourceDuration: 6 };
      let trimmed;
      try { trimmed = await trimVideo(file, range, { signal: new AbortController().signal }); }
      catch (error) { return { unsupported: String(error) }; }
      const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
      const output = new Input({ formats: ALL_FORMATS, source: new BlobSource(trimmed.file) });
      const sourceTrack = (await input.getPrimaryVideoTrack())!;
      const track = (await output.getPrimaryVideoTrack())!;
      const dimensions = [await track.getDisplayWidth(), await track.getDisplayHeight()];
      const sourceDimensions = [await sourceTrack.getDisplayWidth(), await sourceTrack.getDisplayHeight()];
      const beforePacket = (await new EncodedPacketSink(sourceTrack).getPacket(1.5))!;
      const afterPacket = (await new EncodedPacketSink(track).getPacket(.4))!;
      const packetEqual = beforePacket.data.length === afterPacket.data.length && beforePacket.data.every((value, i) => value === afterPacket.data[i]);
      // Check a decoded image inside the cut against the corresponding source time.
      let pixelError: number | null = null;
      let first: number | null = null;
      if (await track.canDecode()) {
      const before = (await new VideoSampleSink(sourceTrack).getSample(1.5))!;
      const after = (await new VideoSampleSink(track).getSample(.4))!;
      const firstSample = (await new VideoSampleSink(track).getSample(0))!;
      first = firstSample.timestamp;
      firstSample.close();
      const canvas = new OffscreenCanvas(dimensions[0], dimensions[1]);
      const context = canvas.getContext('2d')!;
      before.draw(context, 0, 0, canvas.width, canvas.height);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      after.draw(context, 0, 0, canvas.width, canvas.height);
      const copied = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let error = 0;
      for (let i = 0; i < pixels.length; i++) error += Math.abs(pixels[i] - copied[i]);
      before.close(); after.close();
      pixelError = error / pixels.length;
      }
      const stats = await track.computePacketStats();
      const sourceStats = await sourceTrack.computePacketStats();
      const value = { duration: await track.computeDuration(), first, dimensions,
        sourceDimensions, pixelError, packetEqual, frames: stats.packetCount,
        sourceFrames: sourceStats.packetCount, preparationMs: trimmed.preparationMs, audio: !!await output.getPrimaryAudioTrack() };
      (window as any).trimmedFile = trimmed.file;
      input.dispose(); output.dispose();
      return value;
    }, fixture);
    if ('unsupported' in result) {
      if (fixture === 'hevc.mov') {
        // Some B-frame HEVC cuts need references past the requested end. The
        // strict duration guard must reject them for the explicit fallback.
        expect(result.unsupported).toMatch(/LocalTrimError/);
        return;
      }
      throw new Error(result.unsupported);
    }
    expect(result.duration).toBeCloseTo(3.15, 1);
    if (result.first !== null) expect(Math.abs(result.first)).toBeLessThan(.075);
    expect(result.dimensions).toEqual(result.sourceDimensions);
    if (fixture === 'rotated.mov') expect(result.sourceDimensions).toEqual([120, 160]);
    expect(result.packetEqual).toBe(true);
    if (result.pixelError !== null) expect(result.pixelError).toBe(0);
    expect(result.audio).toBe(true);
    if (fixture !== 'variable.mp4') expect(result.frames).toBeGreaterThanOrEqual(94);
    else expect(result.frames).toBeGreaterThanOrEqual(65);
    console.log(fixture, result);
    const downloadPromise = page.waitForEvent('download');
    await page.evaluate(() => {
      const link = document.createElement('a');
      link.href = URL.createObjectURL((window as any).trimmedFile); link.download = 'trimmed.mp4'; link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    await (await downloadPromise).saveAs(info.outputPath('trimmed.mp4'));
  });
}

test('HEVC either trims losslessly or asks before uploading original', async ({ page }) => {
  const storage = await mockUploads(page);
  await page.goto('/tests/fixtures/upload.html');
  await page.locator('#video-upload').setInputFiles('tests/fixtures/hevc.mov');
  await expect(page.getByRole('button', { name: 'Analyze Selected Range' })).toBeEnabled();
  await page.getByRole('button', { name: '+0.5s', exact: true }).first().click();
  await page.getByRole('button', { name: '-0.5s', exact: true }).last().click();
  await page.getByRole('button', { name: 'Analyze Selected Range' }).click();
  await expect(page.getByTestId('phase')).toHaveText(/processing|fallback/);
  if (await page.getByTestId('phase').textContent() === 'fallback') {
    expect(storage.presigns).toHaveLength(0);
    await page.getByRole('button', { name: 'Upload original & trim on server' }).click();
    await expect(page.getByTestId('phase')).toHaveText('processing');
    expect(storage.bodies[0].equals(await readFile('tests/fixtures/hevc.mov'))).toBe(true);
    expect(storage.analyses[0].trim_start_s).toBe(.5);
  } else {
    expect(storage.analyses[0].trim_start_s).toBeNull();
    expect(storage.presigns[0].content_type).toBe('video/mp4');
  }
});

test('production worker bundle can trim without cross-origin-isolation headers', async ({ page }) => {
  const workers = (await readdir('dist/assets')).filter(name => name.startsWith('trimVideo.worker-') && name.endsWith('.js'));
  expect(workers).toHaveLength(1);
  await page.goto('/tests/fixtures/upload.html');
  const result = await page.evaluate(async workerPath => {
    const file = new File([await (await fetch('/tests/fixtures/source.mp4')).blob()], 'source.mp4', { type: 'video/mp4' });
    return await new Promise<any>((resolve, reject) => {
      const worker = new Worker(workerPath, { type: 'module' });
      worker.onerror = error => { worker.terminate(); reject(new Error(error.message)); };
      worker.onmessage = ({ data }) => {
        if (data.type === 'complete') { worker.terminate(); resolve({ duration: data.duration, bytes: data.buffer.byteLength }); }
        if (data.type === 'error') { worker.terminate(); reject(new Error(data.message)); }
      };
      worker.postMessage({ file, range: { start: 1.1, end: 4.25, sourceDuration: 6 } });
    });
  }, `/dist/assets/${workers[0]}`);
  expect(result.duration).toBeCloseTo(3.15, 1);
  expect(result.bytes).toBeGreaterThan(0);
});

// Optional, real lifting footage. The Python comparison consumes these saved
// clips and compares measurements with the backend's current FFmpeg trim path.
for (const filename of ['lat_pulldown_online_log64.mp4', 'pullup_online_log63.mp4',
  'pullup_online_log61.mp4', 'lat_pulldown_online_log57.mp4']) {
  test(`exercise benchmark: ${filename}`, async ({ page }, info) => {
    test.skip(process.env.CLIENT_TRIM_BENCHMARK !== '1', 'Set CLIENT_TRIM_BENCHMARK=1 to process the lifting benchmark clips.');
    await page.goto('/tests/fixtures/upload.html');
    await page.locator('#video-upload').setInputFiles(path.resolve('..', 'data', 'benchmark_videos', filename));
    await expect(page.getByRole('button', { name: 'Analyze Selected Range' })).toBeEnabled();
    const metadata = await page.evaluate(async () => {
      const { trimVideo } = await import('/src/lib/trimVideo.ts');
      const file = document.querySelector<HTMLInputElement>('#video-upload')!.files![0];
      let duration = document.querySelector<HTMLVideoElement>('video')!.duration;
      if (!Number.isFinite(duration) || duration <= 0) {
        const { readVideoDuration } = await import('/src/lib/videoMetadata.ts');
        duration = await readVideoDuration(file, new AbortController().signal);
      }
      const range = { start: .5, end: duration - .5, sourceDuration: duration };
      const result = await trimVideo(file, range, { signal: new AbortController().signal });
      (window as any).trimmedFile = result.file;
      return { range, duration: result.duration,
        preparationMs: result.preparationMs, sourceBytes: file.size, clipBytes: result.file.size };
    });
    const download = page.waitForEvent('download');
    await page.evaluate(() => {
      const link = document.createElement('a');
      link.href = URL.createObjectURL((window as any).trimmedFile); link.download = 'client.mp4'; link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    await (await download).saveAs(info.outputPath('client.mp4'));
    await writeFile(info.outputPath('trim-metadata.json'), JSON.stringify({ filename, browser: info.project.name, ...metadata }, null, 2));
    console.log(filename, metadata);
  });
}
