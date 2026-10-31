import { readFile } from 'node:fs/promises';
import { loadConfig } from './config.mjs';
import { createHttpApp } from './main.mjs';
import { pathToFileURL } from 'node:url';
import { tryOnMediaOrigins } from './try-on.mjs';

export function addPreviewRoutes(app, config) {
if (!['127.0.0.1', 'localhost', '::1'].includes(config.host) || config.devToken || config.publicOrigin) {
  throw new Error('The local verification host requires loopback HOST, no MCP_DEV_TOKEN, and no MCP_PUBLIC_ORIGIN.');
}
app.get('/_dev', (_req, res) => res.type('html').send(`<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KINU TABI 本機橋接驗證</title>
<style>body{font:15px/1.6 system-ui;max-width:960px;margin:20px auto;padding:12px}iframe{width:100%;height:850px;border:1px solid #aaa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f4f2;padding:12px}</style>
<h1>MCP Apps 本機橋接驗證</h1><p>這是開發測試 host，不代表 Codex／ChatGPT 已通過驗收，也沒有 AI 模型。下方是 sandbox iframe 內的真實 UI。</p>
<iframe id="view" title="和服方案選擇" sandbox="allow-scripts"></iframe><h2>最新 AI 上下文（模擬接收）</h2><pre id="context">尚未選擇</pre><h2>明確訊息（模擬接收）</h2><pre id="message">尚未傳送</pre><h2>通訊紀錄</h2><pre id="events"></pre><script type="module" src="/_dev/host.js"></script></html>`));
app.get('/_dev/host.js', async (_req, res) => res.type('js').send(await readFile(new URL('./dist/dev-host.js', import.meta.url), 'utf8')));
app.get('/_dev/view', async (req, res) => {
  const isTryOn = req.query.view === 'try-on';
  const images = isTryOn ? [...config.imageOrigins, ...await tryOnMediaOrigins(config)] : config.imageOrigins;
  res.set('Content-Security-Policy', `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src ${images.join(' ')}; connect-src 'none'; frame-ancestors 'self'`);
  res.type('html').send(await readFile(new URL(isTryOn ? './dist/try-on.html' : './dist/plan-picker.html', import.meta.url), 'utf8'));
});
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
const config = loadConfig();
const app = createHttpApp(config);
addPreviewRoutes(app, config);
const listener = app.listen(config.port, config.host, () => console.log(`Local verification host: http://${config.host}:${config.port}/_dev`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => listener.close(() => process.exit(0)));
}
