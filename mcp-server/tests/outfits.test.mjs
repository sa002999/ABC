import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer as httpServer } from 'node:http';
import { test } from 'node:test';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { createHttpApp } from '../main.mjs';
import { createCatalog } from '../catalog.mjs';
import { loadConfig } from '../config.mjs';

test('public outfit tools preserve backend pricing; per-request credentials are isolated and revoked immediately', async () => {
  const id = '30000000-0000-4000-8000-000000000012';
  const token = 'kt_mcp_' + 'a'.repeat(43);
  let revoked = false, seenBody;
  const upstream = httpServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/api/mcp/member') {
      const valid = req.headers.authorization === `Bearer ${token}` && !revoked;
      res.writeHead(valid ? 200 : 401); res.end(JSON.stringify(valid ? { authenticated: true, channel: 'MCP' } : { error: { code: 'INVALID_MCP_TOKEN', message: 'token 已撤銷' } })); return;
    }
    if (req.url.startsWith('/api/kimonos')) {
      res.end(JSON.stringify({ data: [{ id, name: { 'zh-Hant': '測試和服' }, sku: 'SKU', gender: 'FEMALE', kimonoType: 'KIMONO', styleTags: [], isDemo: true, images: [{ url: '/api/catalog-assets/' + id, kind: 'PRODUCT' }] }], nextPage: null })); return;
    }
    if (req.url === '/api/catalog/outfit-summary') {
      let raw = ''; for await (const chunk of req) raw += chunk; seenBody = JSON.parse(raw);
      res.end(JSON.stringify({ view: 'outfitSummary', ...seenBody, lineItems: [], estimatedTotal: 2800, currency: 'TWD', commonStores: [], isDemo: true, availabilityChecked: false, bookingCreated: false, notice: '無共同門市，請調整搭配' })); return;
    }
    res.writeHead(404); res.end('{}');
  }).listen(0, '127.0.0.1');
  await once(upstream, 'listening');
  const config = loadConfig({ KINUTABI_API_BASE_URL: `http://127.0.0.1:${upstream.address().port}` });
  const listener = createHttpApp(config).listen(0, '127.0.0.1'); await once(listener, 'listening');
  const url = new URL(`http://127.0.0.1:${listener.address().port}/mcp`);
  const anonymous = new Client({ name: 'anonymous', version: '1' });
  const member = new Client({ name: 'member', version: '1' });
  try {
    await anonymous.connect(new StreamableHTTPClientTransport(url));
    await member.connect(new StreamableHTTPClientTransport(url, { requestInit: { headers: { Authorization: `Bearer ${token}` } } }));
    const catalogue = createCatalog(config);
    assert.equal((await catalogue.kimonos({ city: 'KYOTO', planId: id })).kimonos[0].name, '測試和服');
    const guests = [{ guestType: 'ADULT_FEMALE', planId: id, kimonoId: id }];
    const summary = await anonymous.callTool({ name: 'check_outfit_summary', arguments: { city: 'KYOTO', guests } });
    assert.equal(summary.structuredContent.estimatedTotal, 2800);
    assert.deepEqual(seenBody.guests, guests);
    assert.match(summary.content[0].text, /無/);
    assert.equal((await member.callTool({ name: 'get_member_status', arguments: {} })).structuredContent.authenticated, true);
    assert.equal((await anonymous.callTool({ name: 'get_member_status', arguments: {} })).structuredContent.error.code, 'MCP_TOKEN_REQUIRED');
    assert.equal((await anonymous.callTool({ name: 'get_member_status', arguments: { token, userId: id } })).isError, true);
    revoked = true;
    await assert.rejects(member.callTool({ name: 'get_member_status', arguments: {} }));
    assert.equal((await anonymous.callTool({ name: 'list_kimonos', arguments: { city: 'KYOTO', planId: id } })).isError, undefined);
  } finally {
    await Promise.allSettled([anonymous.close(), member.close()]);
    await new Promise(resolve => listener.close(resolve));
    await new Promise(resolve => upstream.close(resolve));
  }
});
