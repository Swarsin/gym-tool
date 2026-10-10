import { useEffect, useRef, useState } from 'react';
import { trimVideo } from '../lib/trimVideo';
import { uploadVideo } from '../lib/uploadVideo';
import { INITIAL_UPLOAD_STATE, UploadState, VideoUploadController } from '../lib/videoUploadController';

export function useVideoUpload(onChange: (state: UploadState) => void) {
  const [state, setState] = useState(INITIAL_UPLOAD_STATE);
  const callback = useRef(onChange);
  callback.current = onChange;
  const controller = useRef<VideoUploadController | null>(null);
  if (!controller.current) {
    controller.current = new VideoUploadController({ trim: trimVideo, upload: uploadVideo }, (next) => {
      setState(next);
      callback.current(next);
    });
  }
  useEffect(() => () => controller.current?.cancel(false), []);
  return { state, controller: controller.current };
}
