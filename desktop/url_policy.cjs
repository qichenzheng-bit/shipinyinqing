'use strict';

function normalizeEndpoint(raw) {
  if (typeof raw !== 'string' || !raw.trim() || raw.length > 400) {
    throw new Error('请输入有效的服务端地址');
  }
  let url;
  try { url = new URL(raw.trim()); }
  catch { throw new Error('服务器地址格式有误'); }
  const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname.toLowerCase());
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) ||
      url.username || url.password || url.search || url.hash ||
      (url.pathname !== '/' && url.pathname !== '') || url.origin === 'null') {
    throw new Error('仅支持 HTTPS 服务器或本机 127.0.0.1');
  }
  return url.origin;
}

function allowedNavigation(expectedOrigin, target) {
  try { return new URL(target).origin === expectedOrigin; }
  catch { return false; }
}

module.exports = { normalizeEndpoint, allowedNavigation };
