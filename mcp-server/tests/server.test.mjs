import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer as httpServer, request as httpRequest } from 'node:http';
import { after, before, test } from 'node:test';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { InMemoryTransport } from '@modelcontextprotocol/server';
import { loadConfig } from '../config.mjs';
import { createHttpApp } from '../main.mjs';
import { createServer, RESOURCE_URI } from '../server.mjs';

const id = '30000000-0000-4000-8000-000000000011';
const missing = '30000000-0000-4000-8000-000000000099';
const plan = { id, name: { 'zh-Hant': '單人和服體驗 <測試>' }, summary: { 'zh-Hant': '方案摘要' }, description: { 'zh-Hant': '範例說明' }, kind: 'SINGLE', basePrice: 1500, currency: 'TWD', durationMinutes: 480, includedItems: ['著裝服務'], isDemo: true, coverImageUrl: '/assets/plan-single.webp',
  stores: [{ id: '10000000-0000-4000-8000-000000000001', city: 'KYOTO', name: { 'zh-Hant': '京都測試門市' } }], kimono: { images: [] } };
let upstream, config, server, client, lastQuery, mode = 'ok';
before(async () => {
  upstream = httpServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/api/plans') lastQuery = url.searchParams;
    res.setHeader('Content-Type', 'application/json');
    if (mode === 'failure') { res.writeHead(500); res.end(JSON.stringify({ secret: 'upstream-private-error' })); return; }
    if (mode === 'invalid') { res.end(JSON.stringify({ data: [{ ...plan, basePrice: -1 }], total: 1, nextPage: null })); return; }
    if (url.pathname === `/api/plans/${missing}`) { res.writeHead(404); res.end('{}'); return; }
    if (url.pathname === `/api/plans/${id}`) { res.end(JSON.stringify(plan)); return; }
    if (url.pathname === '/api/plans') { res.end(JSON.stringify({ data: url.searchParams.get('keyword') === 'nothing' ? [] : [plan], total: url.searchParams.get('keyword') === 'nothing' ? 0 : 1, nextPage: null })); return; }
    res.writeHead(404); res.end('{}');
  });
  upstream.listen(0, '127.0.0.1'); await once(upstream, 'listening');
  config = loadConfig({ KINUTABI_API_BASE_URL: `http://127.0.0.1:${upstream.address().port}` });
  server = createServer(config);
  client = new Client({ name: 'kinu-tabi-test', version: '0.1.0' });
  const [a, b] = InMemoryTransport.createLinkedPair(); await server.connect(b); await client.connect(a);
});
after(async () => { await client?.close(); await server?.close(); await new Promise(resolve => upstream?.close(resolve)); });
const call = (name, args) => client.callTool({ name, arguments: args });
const args = { city: 'KYOTO', partySize: 2 };

test('declares catalogue, member and try-on tools with correct mutation annotations', async () => {
  const { tools } = await client.listTools();
  assert.deepEqual(tools.map(t => t.name).sort(), ['check_outfit_summary','check_party_availability','complete_photo_upload','confirm_booking_hold','confirm_try_on','create_photo_upload','get_kimono_details','get_member_status','get_photo_upload_consent','get_plan_details','get_try_on_job','get_try_on_jobs','list_kimonos','list_plans','prepare_booking','prepare_try_on','show_party_availability','show_plan_picker','show_try_on']);
  assert.ok(tools.filter(t => !['prepare_try_on','confirm_try_on','create_photo_upload','complete_photo_upload','prepare_booking','confirm_booking_hold'].includes(t.name)).every(t => t.annotations.readOnlyHint));
  for(const name of ['get_photo_upload_consent','create_photo_upload','complete_photo_upload','prepare_booking','confirm_booking_hold'])assert.deepEqual(tools.find(t=>t.name===name)._meta.ui.visibility,['app']);
  assert.equal(tools.find(t => t.name==='confirm_try_on').annotations.readOnlyHint,false);
  assert.equal(tools.find(t => t.name === 'show_plan_picker')._meta.ui.resourceUri, RESOURCE_URI);
  assert.ok(!tools.find(t => t.name === 'list_plans')._meta?.ui?.resourceUri);
});
test('queries configured API and returns authoritative unit pricing, demo marker and structured data', async () => {
  const result = await call('list_plans', { ...args, keyword: '和服 & ?city=TOKYO', sort: 'priceAsc' });
  assert.ok(!result.isError);
  assert.equal(lastQuery.get('city'), 'KYOTO');
  assert.equal(lastQuery.get('keyword'), '和服 & ?city=TOKYO');
  assert.equal(lastQuery.get('sort'), 'priceAsc');
  assert.equal(result.structuredContent.filters.partySize, 2);
  const value = result.structuredContent.plans[0];
  assert.equal(value.basePrice, 1500); assert.equal(value.priceUnit, '／人'); assert.equal(value.isDemo, true);
  assert.equal(value.imageUrl, `${config.assetOrigin}/assets/plan-single.webp`);
  assert.equal(result.structuredContent.availabilityChecked, false);
  assert.match(result.content[0].text, /示範資料/);
});
test('validates city, party size and unknown keys before any API call', async () => {
  for (const invalid of [{ city: 'OSAKA', partySize: 2 }, { city: 'KYOTO', partySize: 4 }, { ...args, userId: 'someone-else' }]) {
    const result = await call('list_plans', invalid); assert.equal(result.isError, true);
  }
});
test('selection detail fetches current API data; missing/downstream failures are safe errors', async () => {
  const detail = await call('get_plan_details', { planId: id });
  assert.equal(detail.structuredContent.plan.id, id);
  assert.equal((await call('get_plan_details', { planId: missing })).structuredContent.error.code, 'PLAN_NOT_FOUND');
  mode = 'failure';
  try { const result = await call('list_plans', args); assert.equal(result.isError, true); assert.ok(!JSON.stringify(result).includes('upstream-private-error')); }
  finally { mode = 'ok'; }
});
test('rejects malformed upstream pricing and supports empty search results', async () => {
  mode = 'invalid';
  try { assert.equal((await call('list_plans', args)).structuredContent.error.code, 'INVALID_CATALOG_RESPONSE'); }
  finally { mode = 'ok'; }
  assert.deepEqual((await call('list_plans', { ...args, keyword: 'nothing' })).structuredContent.plans, []);
});
test('omits image URLs outside explicitly configured origins', async () => {
  const original = plan.coverImageUrl;
  try { plan.coverImageUrl = 'https://untrusted.example/track.jpg'; assert.equal((await call('get_plan_details', { planId: id })).structuredContent.plan.imageUrl, null); }
  finally { plan.coverImageUrl = original; }
});
test('serves bundled HTML with MCP Apps MIME and declared resource CSP', async () => {
  const result = await client.readResource({ uri: RESOURCE_URI });
  const resource = result.contents[0];
  assert.equal(resource.mimeType, 'text/html;profile=mcp-app');
  assert.ok(resource.text.includes('<script type="module">'));
  assert.ok(!resource.text.includes('<!-- APP_SCRIPT -->'));
  assert.deepEqual(resource._meta.ui.csp.connectDomains, []);
  assert.ok(resource._meta.ui.csp.resourceDomains.includes(config.apiOrigin));
});
test('configured catalogue CDN appears in both imageUrl and UI CSP; unconfigured CDN stays blocked', async () => {
  const cdnOrigin = 'https://dkwx35rlj68fs.cloudfront.net';
  const original = plan.coverImageUrl;
  const cdnServer = createServer(loadConfig({ KINUTABI_API_BASE_URL: config.apiOrigin, KINUTABI_IMAGE_ORIGINS: cdnOrigin }));
  const cdnClient = new Client({ name: 'cdn-image-test', version: '0.1.0' });
  const [a, b] = InMemoryTransport.createLinkedPair(); await cdnServer.connect(b);
  try {
    plan.coverImageUrl = `${cdnOrigin}/catalog/plan.webp`;
    assert.equal((await call('show_plan_picker', args)).structuredContent.plans[0].imageUrl, null);
    await cdnClient.connect(a);
    const result = await cdnClient.callTool({ name: 'show_plan_picker', arguments: args });
    assert.equal(result.structuredContent.plans[0].imageUrl, plan.coverImageUrl);
    const resource = await cdnClient.readResource({ uri: RESOURCE_URI });
    assert.ok(resource.contents[0]._meta.ui.csp.resourceDomains.includes(cdnOrigin));
  } finally { plan.coverImageUrl = original; await cdnClient.close(); await cdnServer.close(); }
});
test('configuration refuses credential URLs, non-HTTPS remote APIs and ungated remote bindings', () => {
  assert.throws(() => loadConfig({ KINUTABI_API_BASE_URL: 'https://user:secret@example.com' }));
  assert.throws(() => loadConfig({ KINUTABI_API_BASE_URL: 'http://api.example.com' }));
  assert.throws(() => loadConfig({ HOST: '0.0.0.0' }));
  for (const value of ['http://localhost:3001', 'https://*.trycloudflare.com', 'https://example.com/mcp', 'https://user:secret@example.com']) {
    assert.throws(() => loadConfig({ MCP_PUBLIC_ORIGIN: value }));
  }
});
test('allows only an explicitly configured tunnel Host and still rejects untrusted Host/Origin', async () => {
  const tunnelHost = 'calcium-dealt-baker-development.trycloudflare.com';
  const tunneled = loadConfig({ KINUTABI_API_BASE_URL: config.apiOrigin, MCP_PUBLIC_ORIGIN: `https://${tunnelHost}` });
  const initialize = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {
    protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'tunnel-host-test', version: '0.1.0' },
  } });
  async function probe(configuration, host, origin) {
    const listener = createHttpApp(configuration).listen(0, '127.0.0.1'); await once(listener, 'listening');
    try {
      return await new Promise((resolve, reject) => {
        const req = httpRequest({ hostname: '127.0.0.1', port: listener.address().port, path: '/mcp', method: 'POST',
          headers: { Host: host, 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream', ...(origin ? { Origin: origin } : {}) } }, res => {
          let body = ''; res.setEncoding('utf8'); res.on('data', chunk => { body += chunk; });
          res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(body) }));
        });
        req.on('error', reject); req.end(initialize);
      });
    } finally { await new Promise(resolve => listener.close(resolve)); }
  }
  assert.equal((await probe(config, tunnelHost)).status, 403);
  const allowed = await probe(tunneled, tunnelHost);
  assert.equal(allowed.status, 200); assert.equal(allowed.body.result.serverInfo.name, 'kinu-tabi');
  assert.equal((await probe(tunneled, 'another-tunnel.trycloudflare.com')).status, 403);
  assert.equal((await probe(tunneled, tunnelHost, 'https://attacker.example')).status, 403);
  assert.equal((await probe(tunneled, '127.0.0.1')).status, 200);
});
test('stateless HTTP transport initializes and calls tools, rejects browser-origin abuse and enforces developer gate', async () => {
  const listener = createHttpApp(config).listen(0, '127.0.0.1'); await once(listener, 'listening');
  const url = `http://127.0.0.1:${listener.address().port}/mcp`;
  const httpClient = new Client({ name: 'http-test', version: '0.1.0' });
  try {
    await httpClient.connect(new StreamableHTTPClientTransport(new URL(url)));
    assert.equal((await httpClient.callTool({ name: 'list_plans', arguments: args })).structuredContent.plans[0].id, id);
    assert.equal((await fetch(url, { method: 'POST', headers: { Origin: 'https://attacker.example', 'Content-Type': 'application/json' }, body: '{}' })).status, 403);
  } finally { await httpClient.close(); await new Promise(resolve => listener.close(resolve)); }
  const gated = createHttpApp({ ...config, devToken: 'a'.repeat(40) }).listen(0, '127.0.0.1'); await once(gated, 'listening');
  try { assert.equal((await fetch(`http://127.0.0.1:${gated.address().port}/mcp`, { method: 'POST' })).status, 401); }
  finally { await new Promise(resolve => gated.close(resolve)); }
});
