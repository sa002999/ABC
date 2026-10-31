import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/client';
import { InMemoryTransport } from '@modelcontextprotocol/server';
import { loadConfig } from './config.mjs';
import { createServer, RESOURCE_URI } from './server.mjs';

const server = createServer(loadConfig());
const client = new Client({ name: 'kinu-tabi-live-catalog-check', version: '0.1.0' });
const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
await server.connect(serverTransport);
try {
  await client.connect(clientTransport);
  const args = { city: 'KYOTO', partySize: 2 };
  const list = await client.callTool({ name: 'list_plans', arguments: args });
  assert.ok(!list.isError, list.content?.[0]?.text);
  const data = list.structuredContent;
  console.log(JSON.stringify({ liveCatalog: true, city: args.city, count: data.total, returned: data.plans.length, demoCount: data.plans.filter(p => p.isDemo).length }));
  if (data.plans.length) {
    const detail = await client.callTool({ name: 'get_plan_details', arguments: { planId: data.plans[0].id } });
    assert.ok(!detail.isError, detail.content?.[0]?.text);
    assert.equal(detail.structuredContent.plan.id, data.plans[0].id);
    console.log('Live plan detail OK');
  }
  const ui = await client.callTool({ name: 'show_plan_picker', arguments: args });
  assert.ok(!ui.isError);
  const resource = await client.readResource({ uri: RESOURCE_URI });
  assert.ok(resource.contents[0].text.includes('<script type="module">'));
  for (const plan of data.plans) {
    assert.ok(plan.imageUrl, `${plan.name}: image URL missing; check KINUTABI_IMAGE_ORIGINS against the catalogue source.`);
    assert.ok(resource.contents[0]._meta.ui.csp.resourceDomains.includes(new URL(plan.imageUrl).origin));
  }
  console.log('Live picker tool + bundled UI resource OK. Native host rendering still requires separate verification.');
} finally { await client.close(); await server.close(); }
