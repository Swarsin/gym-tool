import { createClient } from '@supabase/supabase-js';
import { API_BASE_URL } from './api';
import { supabaseAnonKey, supabaseUrl } from './supabase';
import { throwIfAborted, validateVideoFile, videoContentType } from './videoFiles';
import type { VideoUploadRequest } from './videoUploadController';
import { fetchWithDeadline } from './fetchWithDeadline';

export async function uploadVideo(request: VideoUploadRequest, signal: AbortSignal): Promise<number> {
  const { file, range, accessToken } = request;
  validateVideoFile(file);
  throwIfAborted(signal);
  const contentType = videoContentType(file);
  // Ensure Blob/File MIME matches the container even when a picker supplied no type.
  const uploadFile = file.type ? file : new File([file], file.name, { type: contentType });
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` };
  let videoUrl: string | null = null;
  try {
    const presign = await fetchWithDeadline(`${API_BASE_URL}/api/v1/storage/upload-url`, {
      method: 'POST', headers, signal,
      body: JSON.stringify({ filename: uploadFile.name, content_type: contentType }),
    }, signal);
    if (presign.status === 401 || presign.status === 403) throw new Error('Your session has expired. Please sign in again.');
    if (presign.ok) {
      const data = await presign.json();
      throwIfAborted(signal);
      if (data.provider === 'r2' && data.upload_url && data.public_url) {
        const response = await fetchWithDeadline(data.upload_url, {
          method: 'PUT', signal, headers: { 'Content-Type': contentType }, body: uploadFile,
        }, signal, 180_000);
        if (!response.ok) throw new Error(`Video upload failed (${response.status}).`);
        videoUrl = data.public_url;
      }
    }
  } catch (error) {
    throwIfAborted(signal); // Cancellation must never start a second storage upload.
    if (error instanceof Error && error.message.startsWith('Your session')) throw error;
    console.warn('R2 upload unavailable; trying the configured storage fallback.', error);
  }
  throwIfAborted(signal);
  if (!videoUrl) {
    // The installed storage SDK has no per-upload AbortSignal. Use an isolated,
    // operation-scoped client/fetch rather than changing the shared auth client.
    const storageClient = createClient(supabaseUrl, supabaseAnonKey, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
      global: { headers: { Authorization: `Bearer ${accessToken}` },
        fetch: (input, init) => fetchWithDeadline(input, init || {}, signal, 180_000) },
    });
    const extension = uploadFile.name.split('.').pop() || 'mp4';
    const path = `uploads/${crypto.randomUUID()}.${extension}`;
    const bucket = storageClient.storage.from('workout-videos');
    const { error } = await bucket.upload(path, uploadFile, { contentType, upsert: false });
    throwIfAborted(signal);
    if (error) throw new Error(error.message || 'Video upload failed.');
    videoUrl = bucket.getPublicUrl(path).data.publicUrl;
  }
  throwIfAborted(signal);
  const response = await fetchWithDeadline(`${API_BASE_URL}/api/v1/analyze`, {
    method: 'POST', headers, signal,
    body: JSON.stringify({
      user_id: request.userId, workout_id: Math.floor(Math.random() * 100000),
      video_storage_path: videoUrl, exercise_name: request.exerciseName, user_height_cm: request.userHeightCm,
      trim_start_s: range?.start ?? null, trim_end_s: range?.end ?? null,
    }),
  }, signal);
  if (!response.ok) throw new Error(`Analysis could not start (${response.status}).`);
  const data = await response.json();
  throwIfAborted(signal);
  if (!Number.isSafeInteger(data.log_id) || data.log_id <= 0) throw new Error('The analysis server returned an invalid job ID.');
  return data.log_id;
}
