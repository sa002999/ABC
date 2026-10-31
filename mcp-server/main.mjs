import { timingSafeEqual } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { createMcpExpressApp } from '@modelcontextprotocol/express';
import { NodeStreamableHTTPServerTransport } from '@modelcontextprotocol/node';
import { StdioServerTransport } from '@modelcontextprotocol/server/stdio';
import { loadConfig } from './config.mjs';
import { createServer } from './server.mjs';

export function createHttpApp(config) {
  const app = createMcpExpressApp({ host: config.host, allowedHosts: config.allowedHosts });
  app.disable('x-powered-by');
  app.get('/health', (_req, res) => res.json({ status: 'ok', milestone: 'ai-try-on', memberActions: true }));
  app.all('/mcp', async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    if (config.devToken) {
      const actual = Buffer.from(req.headers.authorization || '');
      const expected = Buffer.from(`Bearer ${config.devToken}`);
      if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
        return res.status(401).json({ error: 'DEVELOPMENT_TOKEN_REQUIRED' });
      }
    }
    const authorization = req.headers.authorization;
    if (authorization && !config.devToken) {
      if (!/^Bearer kt_mcp_[A-Za-z0-9_-]{43}$/.test(authorization)) return res.status(401).json({ error: 'INVALID_MCP_TOKEN' });
      try {
        const validation = await fetch(new URL('/api/mcp/member', config.apiOrigin), {
          headers: { Authorization: authorization }, redirect: 'error', signal: AbortSignal.timeout(10000),
        });
        if (!validation.ok) return res.status([401,403].includes(validation.status) ? 401 : 503).json({ error: 'MCP_AUTH_UNAVAILABLE_OR_INVALID' });
      } catch { return res.status(503).json({ error: 'MCP_AUTH_UNAVAILABLE' }); }
    }
    // Credential belongs only to this HTTP request, never shared between clients or exposed as a tool argument.
    const server = createServer({ ...config, memberAuthorization: config.devToken ? undefined : authorization });
    const transport = new NodeStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    res.on('close', () => { void transport.close().catch(() => {}); void server.close().catch(() => {}); });
    try {
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch {
      if (!res.headersSent) res.status(500).json({ jsonrpc: '2.0', id: null, error: { code: -32603, message: 'MCP request failed.' } });
    }
  });
  return app;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const config = loadConfig();
  if (process.argv.includes('--stdio')) {
    await createServer(config).connect(new StdioServerTransport());
  } else {
    const listener = createHttpApp(config).listen(config.port, config.host, () => console.error(`KINU TABI MCP: http://${config.host}:${config.port}/mcp`));
    listener.on('error', () => { console.error('Could not start MCP HTTP listener.'); process.exitCode = 1; });
    for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => listener.close(() => process.exit(0)));
  }
}
