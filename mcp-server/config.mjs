const loopback = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

export function origin(value, label) {
  const url = new URL(value);
  if (url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
      (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback.has(url.hostname)))) {
    throw new Error(`${label} must be an HTTPS origin (HTTP is allowed only on loopback).`);
  }
  return url.origin;
}

export function loadConfig(env = process.env) {
  const apiOrigin = origin(env.KINUTABI_API_BASE_URL || 'http://127.0.0.1:8000', 'KINUTABI_API_BASE_URL');
  const webOrigin = origin(env.KINUTABI_WEB_BASE_URL || 'http://127.0.0.1:8000', 'KINUTABI_WEB_BASE_URL');
  const assetOrigin = origin(env.KINUTABI_ASSET_BASE_URL || apiOrigin, 'KINUTABI_ASSET_BASE_URL');
  const imageOrigins = [...new Set([apiOrigin, assetOrigin, ...(env.KINUTABI_IMAGE_ORIGINS || '')
    .split(',').map(s => s.trim()).filter(Boolean).map(s => origin(s, 'KINUTABI_IMAGE_ORIGINS'))])];
  const host = env.HOST || '127.0.0.1';
  const port = Number(env.PORT || 3001);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be 1–65535.');
  const devToken = env.MCP_DEV_TOKEN || '';
  if (devToken && devToken.length < 32) throw new Error('MCP_DEV_TOKEN must have at least 32 characters.');
  if (!loopback.has(host) && !devToken) throw new Error('Non-loopback binding requires MCP_DEV_TOKEN.');
  const publicOrigin = env.MCP_PUBLIC_ORIGIN ? origin(env.MCP_PUBLIC_ORIGIN, 'MCP_PUBLIC_ORIGIN') : undefined;
  if (publicOrigin && (new URL(publicOrigin).protocol !== 'https:' || new URL(publicOrigin).hostname.includes('*'))) {
    throw new Error('MCP_PUBLIC_ORIGIN must be one exact HTTPS origin, without wildcards.');
  }
  const allowedHosts = publicOrigin ? ['localhost', '127.0.0.1', '[::1]', new URL(publicOrigin).hostname] : undefined;
  return { apiOrigin, webOrigin, assetOrigin, imageOrigins, host, port, devToken, publicOrigin, allowedHosts };
}
