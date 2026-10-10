import { createServer } from 'node:http';

// A real HTTP receiver is needed because WebKit's automation protocol does not
// expose Blob PUT bodies through request.postDataBuffer(). Never contacts R2.
const captures = new Map();
createServer((request, response) => {
  response.setHeader('Access-Control-Allow-Origin', '*');
  response.setHeader('Access-Control-Allow-Methods', 'PUT, GET, OPTIONS');
  response.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  const url = new URL(request.url, 'http://127.0.0.1:4178');
  if (request.method === 'OPTIONS') { response.writeHead(204).end(); return; }
  if (url.pathname === '/health') { response.end('ready'); return; }
  if (url.pathname === '/capture') {
    response.end(captures.get(url.searchParams.get('key')) || Buffer.alloc(0));
    return;
  }
  if (request.method !== 'PUT' || url.pathname !== '/test-upload') {
    response.writeHead(404).end(); return;
  }
  const chunks = [];
  let size = 0;
  request.on('data', chunk => {
    size += chunk.length;
    if (size > 50 * 1024 * 1024) { request.destroy(); return; }
    chunks.push(chunk);
  });
  request.on('end', () => {
    captures.set(url.searchParams.get('key'), Buffer.concat(chunks));
    response.writeHead(200, { 'Content-Type': 'application/json' }).end('{"ok":true}');
  });
}).listen(4178, '127.0.0.1');
