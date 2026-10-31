// Local verification host, not a ChatGPT/Codex integration or production host.
import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

const events = document.getElementById('events');
function log(message) { events.textContent += `${message}\n`; }
try {
  const client = new Client({ name: 'kinu-tabi-local-test-host', version: '0.1.0' });
  await client.connect(new StreamableHTTPClientTransport(new URL('/mcp', location.href)));
  log('MCP client connected');
  const bridge = new AppBridge(client, { name: 'Local test host', version: '0.1.0' }, { serverTools: {}, updateModelContext: { text: {} }, message: { text: {} } });
  bridge.onupdatemodelcontext = async params => {
    document.getElementById('context').textContent = JSON.stringify(params, null, 2);
    log('UI selection context received (no model is running in this test host)');
    return {};
  };
  bridge.onmessage = async params => {
    document.getElementById('message').textContent = JSON.stringify(params, null, 2);
    log('Explicit message received (not sent to any real conversation)');
    return {};
  };
  bridge.oncalltool = async params => { log(`UI tools/call: ${params.name}`); return client.callTool(params); };
  const frame = document.getElementById('view');
  const query = new URLSearchParams(location.search);
  const tryOn = query.get('view') === 'try-on';
  bridge.oninitialized = async () => {
    try {
      log('MCP Apps iframe initialized');
      const args = tryOn ? { planId: query.get('plan'), kimonoId: query.get('kimono') } : { city: 'KYOTO', partySize: 2 };
      await bridge.sendToolInput({ arguments: args });
      await bridge.sendToolResult(await client.callTool({ name: tryOn ? 'show_try_on' : 'show_plan_picker', arguments: args }));
      log('Initial tool result delivered');
    } catch { log('Initial data delivery failed'); }
  };
  await bridge.connect(new PostMessageTransport(frame.contentWindow, frame.contentWindow));
  frame.src = '/_dev/view' + (tryOn ? '?view=try-on' : '');
} catch { log('Local bridge failed to initialize'); }
