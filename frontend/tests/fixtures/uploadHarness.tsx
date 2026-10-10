import React from 'react';
import { createRoot } from 'react-dom/client';
import UploadZone from '../../src/components/UploadZone';
import VideoPreparationPanel from '../../src/components/VideoPreparationPanel';
import { useVideoUpload } from '../../src/hooks/useVideoUpload';
import '../../src/index.css';

function Harness() {
  const upload = useVideoUpload(() => {});
  return <>
    {upload.state.phase === 'idle' && <UploadZone accessToken="test-access-token" userId="test-user"
      onSubmit={request => { void upload.controller.start(request); }} onShowToast={() => {}} />}
    {['preparing', 'fallback'].includes(upload.state.phase) && <VideoPreparationPanel state={upload.state}
      onCancel={() => upload.controller.cancel()} onRetry={() => { void upload.controller.retry(); }}
      onServerFallback={() => { void upload.controller.useServerTrim(); }} />}
    {upload.state.phase === 'uploading' && <button onClick={() => upload.controller.cancel()}>Cancel upload</button>}
    <p data-testid="phase">{upload.state.phase}</p>
    {upload.state.error && <p data-testid="error">{upload.state.error}</p>}
  </>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
