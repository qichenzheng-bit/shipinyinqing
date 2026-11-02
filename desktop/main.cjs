'use strict';
const { app, BrowserWindow, ipcMain, safeStorage, session } = require('electron');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { NativeServices } = require('./native_services.cjs');
const { normalizeEndpoint, allowedNavigation } = require('./url_policy.cjs');
const { createBridge } = require('./cli_bridge.cjs');
const { login: startVendorLogin, status: vendorAuthStatus, models: vendorModels } = require('./ai_auth.cjs');

const APP_ID = 'cn.weiguang.math';
const LOCAL_URL = 'http://127.0.0.1:8000';
let launcher = null;
let studio = null;
let starting = false;
let appClosing = false;
let cliBridge = null;
let nativeServices = null;

app.setAppUserModelId(APP_ID);
const hasLock = app.requestSingleInstanceLock();
if (!hasLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const active = studio && !studio.isDestroyed() ? studio : launcher;
    if (active && !active.isDestroyed()) {
      if (active.isMinimized()) active.restore();
      active.show();
      active.focus();
    }
  });
}

function prefsPath() { return path.join(app.getPath('userData'), 'launcher.json'); }
function secretsPath() { return path.join(app.getPath('userData'), 'local-secrets.bin'); }
function serviceRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'service')
    : path.resolve(__dirname, '..');
}
function readPrefs() {
  try {
    const prefs = JSON.parse(fs.readFileSync(prefsPath(), 'utf8'));
    return {
      mode: prefs.mode === 'remote' ? 'remote' : 'local',
      url: prefs.mode === 'remote' ? normalizeEndpoint(prefs.url) : LOCAL_URL,
    };
  } catch {
    return { mode: 'local', url: LOCAL_URL };
  }
}
function writePrefs(prefs) {
  const target = prefsPath();
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temporary = target + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(prefs), { mode: 0o600 });
  fs.renameSync(temporary, target);
}
function keyMaterial() {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Windows 凭据加密不可用；无法安全生成本地数据库密钥。');
  }
  const target = secretsPath();
  if (fs.existsSync(target)) {
    try {
      const content = safeStorage.decryptString(fs.readFileSync(target));
      const result = JSON.parse(content);
      for (const name of ['POSTGRES_PASSWORD', 'WEIGUANG_API_TOKEN', 'WEIGUANG_MODEL_MASTER_KEY']) {
        if (!result[name] || typeof result[name] !== 'string') throw Error('missing');
      }
      if (!result.WEIGUANG_CLI_BRIDGE_TOKEN) {
        // Preserve existing DB and encryption secrets across upgrades.
        result.WEIGUANG_CLI_BRIDGE_TOKEN = crypto.randomBytes(48).toString('hex');
        const upgradePath = target + '.upgrade';
        fs.writeFileSync(upgradePath, safeStorage.encryptString(JSON.stringify(result)),
          { mode: 0o600, flag: 'wx' });
        fs.renameSync(upgradePath, target);
      }
      return result;
    } catch {
      throw new Error('原有 Windows 凭据无法解密。为保护已有数据库，不会自动重置密码。');
    }
  }
  const data = {
    POSTGRES_PASSWORD: crypto.randomBytes(32).toString('hex'),
    WEIGUANG_API_TOKEN: crypto.randomBytes(48).toString('hex'),
    WEIGUANG_CLI_BRIDGE_TOKEN: crypto.randomBytes(48).toString('hex'),
    // Fernet requires padded URL-safe base64 representing 32 random bytes.
    WEIGUANG_MODEL_MASTER_KEY: crypto.randomBytes(32).toString('base64')
      .replace(/\+/g, '-').replace(/\//g, '_'),
  };
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, safeStorage.encryptString(JSON.stringify(data)), {
    mode: 0o600, flag: 'wx',
  });
  return data;
}

function progress(message) {
  if (launcher && !launcher.isDestroyed()) launcher.webContents.send('wg:progress', message);
}
async function waitForHealth(origin, attempts = 2) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const r = await fetch(origin + '/health', {
        redirect: 'error', signal: AbortSignal.timeout(2500),
      });
      if (r.ok) return;
    } catch { /* retry while native server starts */ }
    if (i + 1 < attempts) await new Promise(resolve => setTimeout(resolve, 1500));
  }
  throw new Error('Windows 本地服务未就绪，请使用“启动并进入工作台”完成原生引擎启动。');
}
async function verifyLocalBackend(token) {
  const nonce = crypto.randomBytes(32).toString('hex');
  const r = await fetch(LOCAL_URL + '/api/v1/desktop/handshake', {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nonce }),
  });
  if (!r.ok) throw new Error('当前本机端口不是由此 App 管理的微光数学服务。');
  const response = await r.json();
  const expected = crypto.createHmac('sha256', token).update('weiguang-desktop:' + nonce).digest('hex');
  const received = String(response.proof || '');
  if (!/^[a-f0-9]{64}$/.test(received) ||
      !crypto.timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(received, 'hex'))) {
    throw new Error('本地服务身份校验失败；已阻止发送登录凭据。');
  }
}
async function autoLogin(token) {
  await verifyLocalBackend(token);
  const response = await fetch(LOCAL_URL + '/api/v1/auth/login', {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!response.ok) throw new Error('本地服务已连接，但登录凭据不匹配。');
  const cookie = response.headers.get('set-cookie') || '';
  const match = /^wg_session=([^;]+)/.exec(cookie);
  if (!match) throw new Error('本地服务没有返回有效登录会话。');
  await session.defaultSession.cookies.set({
    url: LOCAL_URL + '/', name: 'wg_session', value: match[1],
    path: '/', httpOnly: true, secure: false, sameSite: 'strict',
  });
}

function installWebSecurity(win, origin) {
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (event, target) => {
    if (!allowedNavigation(origin, target)) event.preventDefault();
  });
  win.webContents.on('will-redirect', (event, target) => {
    if (!allowedNavigation(origin, target)) event.preventDefault();
  });
}
async function showStudio(origin) {
  if (studio && !studio.isDestroyed()) {
    studio.show();
    studio.focus();
    return;
  }
  studio = new BrowserWindow({
    width: 1440, height: 900, minWidth: 990, minHeight: 660,
    show: false, title: '微光数学',
    backgroundColor: '#ffffff',
    icon: path.join(__dirname, 'build', 'app.png'),
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false, contextIsolation: true,
      sandbox: true, webSecurity: true,
      preload: origin===LOCAL_URL ? path.join(__dirname, 'studio_preload.cjs') : undefined,
      webviewTag: false, allowRunningInsecureContent: false,
    },
  });
  installWebSecurity(studio, origin);
  studio.once('ready-to-show', () => {
    studio.show();
    if (launcher && !launcher.isDestroyed()) launcher.hide();
  });
  studio.on('closed', () => {
    studio = null;
    if (!appClosing && launcher && !launcher.isDestroyed()) launcher.show();
  });
  try {
    await studio.loadURL(origin + '/');
  } catch {
    if (studio && !studio.isDestroyed()) studio.destroy();
    throw new Error('工作台未能加载，请检查服务端地址和证书。');
  }
}

function startLocalCliBridge(secrets) {
  if (cliBridge) cliBridge.stop();
  cliBridge = createBridge({origin:LOCAL_URL,authToken:secrets.WEIGUANG_API_TOKEN,
    bridgeToken:secrets.WEIGUANG_CLI_BRIDGE_TOKEN});
  cliBridge.start();
}
function stopLocalCliBridge() {
  if (cliBridge) cliBridge.stop();
  cliBridge = null;
}

async function launchLocal() {
  if (starting) throw new Error('本地服务正在启动');
  starting = true;
  try {
    const root = serviceRoot();
    const runtime = app.isPackaged
      ? path.join(process.resourcesPath, 'runtime')
      : path.resolve(__dirname, 'native_runtime');
    const secrets = keyMaterial();
    if (!nativeServices) nativeServices = new NativeServices({
      serviceRoot: root, runtimeRoot: runtime,
      userDir: path.join(app.getPath('userData'), 'native-services'),
      secrets, progress,
    });
    await nativeServices.start();
    progress('检查本地服务身份与健康状态…');
    await waitForHealth(LOCAL_URL, 80);
    await autoLogin(secrets.WEIGUANG_API_TOKEN);
    startLocalCliBridge(secrets);
    writePrefs({ mode: 'local', url: LOCAL_URL });
    await showStudio(LOCAL_URL);
    progress('Windows 原生视频引擎已连接');
    return { ok: true };
  } finally {
    starting = false;
  }
}
async function connectLocal() {
  const secrets = keyMaterial();
  await waitForHealth(LOCAL_URL);
  await autoLogin(secrets.WEIGUANG_API_TOKEN);
  startLocalCliBridge(secrets);
  writePrefs({ mode: 'local', url: LOCAL_URL });
  await showStudio(LOCAL_URL);
  return { ok: true };
}
async function connectRemote(raw) {
  stopLocalCliBridge();
  const origin = normalizeEndpoint(raw);
  await waitForHealth(origin);
  writePrefs({ mode: 'remote', url: origin });
  await showStudio(origin);
  return { ok: true };
}

function onlyLocalStudio(handler) {
  return async (event, kind) => {
    if (!studio || studio.isDestroyed() || event.sender !== studio.webContents ||
        !event.senderFrame || event.senderFrame !== studio.webContents.mainFrame ||
        new URL(event.senderFrame.url).origin !== LOCAL_URL) {
      throw new Error('CLI_ACCOUNT_LOGIN_LOCAL_STUDIO_ONLY');
    }
    return handler(kind);
  };
}
function onlyLauncher(handler) {
  return async (event, ...args) => {
    const expected = pathToFileURL(path.join(__dirname, 'launcher.html')).href;
    if (!event.senderFrame || event.senderFrame.url.split(/[?#]/)[0] !== expected) {
      throw new Error('未经授权的桌面窗口请求');
    }
    try { return await handler(...args); }
    catch (error) {
      progress(error && error.message ? error.message : '操作失败');
      return { ok: false, error: error && error.message ? error.message : '操作失败' };
    }
  };
}
function createLauncher() {
  launcher = new BrowserWindow({
    width: 760, height: 590, minWidth: 680, minHeight: 520,
    title: '微光数学 · 启动',
    backgroundColor: '#ffffff', autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false, contextIsolation: true,
      sandbox: true, webSecurity: true,
    },
  });
  const fileOrigin = pathToFileURL(path.join(__dirname, 'launcher.html')).href;
  launcher.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  launcher.webContents.on('will-navigate', (event, target) => {
    if (target !== fileOrigin) event.preventDefault();
  });
  launcher.on('closed', () => { launcher = null; });
  launcher.loadFile(path.join(__dirname, 'launcher.html'));
}

if (hasLock) {
  app.whenReady().then(() => {
    session.defaultSession.setPermissionRequestHandler((_wc, _permission, done) => done(false));
    ipcMain.handle('wg:status', onlyLauncher(() => ({
      ok: true, ...readPrefs(), packaged: app.isPackaged,
      platform: process.platform,
    })));
    ipcMain.handle('wg:start-local', onlyLauncher(launchLocal));
    ipcMain.handle('wg:connect-local', onlyLauncher(connectLocal));
    ipcMain.handle('wg:connect-remote', onlyLauncher(connectRemote));
    ipcMain.handle('wg:ai-login', onlyLocalStudio(startVendorLogin));
    ipcMain.handle('wg:ai-status', onlyLocalStudio(vendorAuthStatus));
    ipcMain.handle('wg:ai-models', onlyLocalStudio(kind=>({models:vendorModels(kind),source:'local_suggestions'})));
    createLauncher();
  });
  app.on('before-quit', () => {
    appClosing = true;
    stopLocalCliBridge();
    if (nativeServices) nativeServices.stop().catch(() => {});
  });
  app.on('window-all-closed', () => app.quit());
}
