'use strict';
/**
 * Windows-only local production runtime. No Docker daemon, WSL2 or Redis.
 * The installer carries a CPython/Manim/FFmpeg/PostgreSQL environment and a
 * verified MiKTeX portable installer. Mutable data stays in Electron userData.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const os = require('node:os');
const { spawn, execFile } = require('node:child_process');
const { promisify } = require('node:util');
const exec = promisify(execFile);
const HOST = '127.0.0.1';
const PG_PORT = '55432';
const API_PORT = '8000';

function executable(root, name) {
  const candidates = [
    path.join(root, 'Library', 'bin', name),
    path.join(root, 'Scripts', name),
    path.join(root, 'bin', name),
    path.join(root, name),
  ];
  const result = candidates.find(p => fs.existsSync(p));
  if (!result) throw new Error('Windows 运行时缺少 ' + name + '，安装包不完整。');
  return result;
}
function latexCommand(texRoot) {
  // MiKTeX portable installer versions have used both bin and bin/x64.
  const candidates = [
    path.join(texRoot, 'miktex', 'bin', 'x64', 'latex.exe'),
    path.join(texRoot, 'miktex', 'bin', 'latex.exe'),
    path.join(texRoot, 'texmfs', 'install', 'miktex', 'bin', 'x64', 'latex.exe'),
    path.join(texRoot, 'bin', 'x64', 'latex.exe'),
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  const visit = (directory, depth) => {
    if (depth > 5 || !fs.existsSync(directory)) return null;
    for (const ent of fs.readdirSync(directory, { withFileTypes: true })) {
      if (ent.isSymbolicLink()) continue;
      const full = path.join(directory, ent.name);
      if (ent.isFile() && ent.name.toLowerCase() === 'latex.exe') return full;
      if (ent.isDirectory()) {
        const found = visit(full, depth + 1);
        if (found) return found;
      }
    }
    return null;
  };
  return visit(texRoot, 0);
}

/** Keep all MiKTeX roots disjoint. v2 also avoids the broken v1
 * user-install=tex-runtime / user-config=tex-runtime\\config nesting.
 * v3/v4 are reserved for non-destructive recovery after interrupted installs.
 */
function texLayout(userDir, version = 2) {
  const base = path.join(userDir, 'tex-runtime-v' + version);
  return {
    base,
    install: path.join(base, 'install'),
    config: path.join(base, 'config'),
    data: path.join(base, 'data'),
  };
}
function texInstallerArgs(roots) {
  const dirs = [roots.install, roots.config, roots.data].map(p => path.resolve(p));
  for (let i = 0; i < dirs.length; i++) {
    for (let j = i + 1; j < dirs.length; j++) {
      const rel = path.relative(dirs[i], dirs[j]);
      const inverse = path.relative(dirs[j], dirs[i]);
      if (!rel || !inverse ||
          (!rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel)) ||
          (!inverse.startsWith('..' + path.sep) && inverse !== '..' && !path.isAbsolute(inverse))) {
        throw new Error('MIKTEX_ROOT_DIRECTORY_OVERLAP');
      }
    }
  }
  return [
    '--private', '--unattended', '--package-set=basic',
    '--user-install=' + roots.install,
    '--user-config=' + roots.config,
    '--user-data=' + roots.data,
  ];
}
function hasContent(directory) {
  if (!fs.existsSync(directory)) return false;
  // Fail closed on unreadable directories rather than overwriting user data.
  try { return fs.readdirSync(directory).length > 0; }
  catch { return true; }
}

async function run(exe, args, options = {}) {
  return exec(exe, args, {
    timeout: options.timeout || 120000, windowsHide: true,
    cwd: options.cwd, env: options.env, maxBuffer: 2 * 1024 * 1024,
  });
}
class NativeServices {
  constructor({ serviceRoot, runtimeRoot, userDir, secrets, progress = () => {}, skipTexBootstrap = false, texRunner = run, localStateRoot = null }) {
    this.serviceRoot = serviceRoot;
    this.runtimeRoot = runtimeRoot;
    this.userDir = userDir;
    this.secrets = secrets;
    this.progress = progress;
    this.pythonProcess = null;
    this.startedPostgres = false;
    this.stopRequested = false;
    this.skipTexBootstrap = skipTexBootstrap;
    this.texRunner = texRunner;
    // Native PostgreSQL CLI may not decode non-ASCII paths on some Windows locales.
    this.localStateRoot = localStateRoot || path.join(
      process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
      'WeiGuangMath', 'native-services');
  }
  engine() { return path.join(this.runtimeRoot, 'engine'); }
  // Keep child processes out of localized Electron userData; MiKTeX and
  // PostgreSQL native tools can fail to emit logs under non-ASCII cwd.
  backendCwd() { return this.localStateRoot; }
  /** An actual one-page LaTeX compile, not just an exe existence check.
   * Isolated temporary files are the only files removed by this method.
   */
  async checkTex(root) {
    const latex = latexCommand(root);
    if (!latex) return null;
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'weiguang-tex-smoke-'));
    try {
      fs.writeFileSync(path.join(temp, 'probe.tex'),
        '\\documentclass{article}\n\\begin{document}\n$x^2+1$\n\\end{document}\n');
      await this.texRunner(latex, [
        '-interaction=nonstopmode', '-halt-on-error', '-no-shell-escape', 'probe.tex',
      ], { cwd: temp, timeout: 90000 });
      return fs.existsSync(path.join(temp, 'probe.dvi')) ? path.dirname(latex) : null;
    } catch {
      return null;
    } finally {
      fs.rmSync(temp, { recursive: true, force: true });
    }
  }
  async ensureTex() {
    const layouts = [2, 3, 4].map(v => texLayout(this.userDir, v));
    // A complete installation is reused; no repeated download or installation.
    for (const layout of layouts) {
      // A present but broken installation must not trigger another long setup.
      // Only a directory without latex.exe is eligible for isolated recovery.
      const existing = latexCommand(layout.install);
      if (!existing) continue;
      const ready = await this.checkTex(layout.install);
      if (ready) return ready;
      throw new Error('已检测到 MiKTeX，但公式编译未通过；已停止重复安装，保留现场以便诊断。');
    }
    // Preserve/reuse a fully working v1 installation, but never reuse a
    // half-initialized parent root (the original source of the setup error).
    const legacy = await this.checkTex(path.join(this.userDir, 'tex-runtime'));
    if (legacy) return legacy;

    const installer = path.join(this.runtimeRoot, 'basic-miktex-25.12-x64.exe');
    if (!fs.existsSync(installer)) throw new Error('安装包缺少 MiKTeX 公式运行时，未进行重复下载。');

    // Never overwrite an incomplete prior attempt or touch its configuration.
    const available = layouts.find(layout =>
      ![layout.install, layout.config, layout.data].some(hasContent));
    if (!available) {
      throw new Error('MiKTeX 多次初始化中断；旧目录均已保留，已停止重复安装，请检查诊断日志。');
    }
    const args = texInstallerArgs(available); // Validated before the costly setup.
    fs.mkdirSync(available.base, { recursive: true });
    this.progress('首次配置 MiKTeX 公式组件（独立安装、配置与数据目录）…');
    try {
      await this.texRunner(installer, args,
        { cwd: available.base, timeout: 20 * 60 * 1000 });
    } catch (error) {
      throw new Error('MiKTeX 初始化未成功，已保留现场以便安全重试：' + String(error.message).slice(0, 180));
    }
    // The basic MiKTeX installer defaults to prompting or refusing when
    // Manim's standalone/babel/amsmath packages are not yet present.
    // Configure unattended, on-demand package installation BEFORE declaring
    // this TeX environment usable. Never reinstall an existing broken TeX.
    const latex = latexCommand(available.install);
    const initexmf = latex ? path.join(path.dirname(latex), 'initexmf.exe') : null;
    if (!initexmf || !fs.existsSync(initexmf)) {
      throw new Error('MiKTeX 缺少宏包配置工具 initexmf，已停止初始化并保留现场。');
    }
    try {
      await this.texRunner(initexmf, ['--set-config-value=[MPM]AutoInstall=yes'],
        { cwd: available.base, timeout: 90000 });
    } catch (error) {
      throw new Error('MiKTeX 自动宏包安装配置失败，保留现场：' + String(error.message).slice(0, 160));
    }
    const ready = await this.checkTex(available.install);
    if (!ready) throw new Error('MiKTeX 未通过真实 LaTeX 公式编译验收；已保留安装现场，避免误报成功。');
    return ready;
  }
  processEnv(texBin) {
    const engine = this.engine();
    const paths = [
      path.join(engine, 'Library', 'bin'),
      path.join(engine, 'Scripts'),
      engine, texBin,
    ];
    const backend = path.join(this.serviceRoot, 'backend', 'src');
    const animation = path.join(this.serviceRoot, 'animation_engine', 'src');
    const teacher = path.join(this.serviceRoot, 'teacher_module', 'src');
    const director = path.join(this.serviceRoot, 'visual_director', 'src');
    // MiKTeX parses an absolute TeX input path as TeX tokens. Windows 8.3
    // aliases such as C:\\Users\\RUNNER~1 are NOT safe: '~' becomes a TeX
    // active character, causing "I can't find file C:/Users/RUNNER".
    // Python tempfile and Manim must not inherit a short-path TEMP/TMP.
    const nativeTemp = path.join(this.localStateRoot, 'temp');
    fs.mkdirSync(nativeTemp, { recursive: true });
    return {
      ...process.env,
      TEMP: nativeTemp,
      TMP: nativeTemp,
      TMPDIR: nativeTemp,
      PATH: [...paths, process.env.PATH || ''].join(path.delimiter),
      PYTHONPATH: [backend, animation, teacher, director].join(path.delimiter),
      PYTHONNOUSERSITE: '1',
      PYTHONDONTWRITEBYTECODE: '1',
      DATABASE_URL: `postgresql+psycopg://weiguang:${encodeURIComponent(this.secrets.POSTGRES_PASSWORD)}@${HOST}:${PG_PORT}/weiguang`,
      WEIGUANG_STORAGE: path.join(this.userDir, 'lessondata'),
      WEIGUANG_LOCAL_DEV: '1',
      WEIGUANG_NATIVE_QUEUE: '1',
      WEIGUANG_API_TOKEN: this.secrets.WEIGUANG_API_TOKEN,
      WEIGUANG_CLI_BRIDGE_TOKEN: this.secrets.WEIGUANG_CLI_BRIDGE_TOKEN,
      WEIGUANG_MODEL_MASTER_KEY: this.secrets.WEIGUANG_MODEL_MASTER_KEY,
      WEIGUANG_TEACHER_ENABLED: '0',
      WEIGUANG_EDIT_AI_ENABLED: '0',
      PGHOST: HOST, PGPORT: PG_PORT, PGUSER: 'weiguang',
      PGPASSWORD: this.secrets.POSTGRES_PASSWORD,
    };
  }
  postgresDirectory() {
    const legacy = path.join(this.userDir, 'postgresql17');
    // Preserve old, initialized clusters rather than silently switching data.
    if (fs.existsSync(path.join(legacy, 'PG_VERSION'))) return legacy;
    return path.join(this.localStateRoot, 'postgresql17');
  }
  async startPostgres(env) {
    const engine = this.engine();
    const pgctl = executable(engine, 'pg_ctl.exe');
    const pgdir = this.postgresDirectory();
    const logfile = path.join(this.localStateRoot, 'postgresql.log');
    fs.mkdirSync(this.localStateRoot, { recursive: true });
    fs.mkdirSync(this.userDir, { recursive: true });
    if (!fs.existsSync(path.join(pgdir, 'PG_VERSION'))) {
      if (fs.existsSync(pgdir) && fs.readdirSync(pgdir).length) {
        throw new Error('PostgreSQL 数据目录存在未完成的初始化，已保留原始数据，请先备份检查。');
      }
      this.progress('初始化本地 PostgreSQL 17 数据库…');
      const passfile = path.join(this.localStateRoot, 'initdb-' + crypto.randomBytes(8).toString('hex') + '.tmp');
      fs.writeFileSync(passfile, this.secrets.POSTGRES_PASSWORD + '\n', { flag: 'wx', mode: 0o600 });
      try {
        await run(executable(engine, 'initdb.exe'), [
          '-D', pgdir, '-U', 'weiguang', '--encoding=UTF8',
          '--auth-host=scram-sha-256', '--auth-local=scram-sha-256',
          '--pwfile=' + passfile,
        ], { env, timeout: 120000 });
      } finally {
        fs.rmSync(passfile, { force: true });
      }
    }
    let alreadyRunning = false;
    try {
      await run(pgctl, ['-D', pgdir, 'status'], { env, timeout: 10000 });
      alreadyRunning = true;
    } catch { /* not running for this data directory */ }
    if (!alreadyRunning) {
      this.progress('启动 PostgreSQL 本地服务…');
      await run(pgctl, [
        '-D', pgdir, '-l', logfile, '-w', '-t', '60',
        '-o', `-h ${HOST} -p ${PG_PORT}`, 'start',
      ], { env, timeout: 90000 });
      this.startedPostgres = true;
    }
    // Authentication also detects a foreign PostgreSQL instance on our port.
    const psql = executable(engine, 'psql.exe');
    await run(psql, ['-X', '-h', HOST, '-p', PG_PORT, '-U', 'weiguang',
      '-d', 'postgres', '-tAc', 'SELECT 1'], { env, timeout: 10000 });
    const query = await run(psql, ['-X', '-h', HOST, '-p', PG_PORT,
      '-U', 'weiguang', '-d', 'postgres', '-tAc',
      "SELECT 1 FROM pg_database WHERE datname='weiguang'"], { env });
    if (query.stdout.trim() !== '1') {
      await run(executable(engine, 'createdb.exe'), [
        '-h', HOST, '-p', PG_PORT, '-U', 'weiguang', 'weiguang',
      ], { env, timeout: 20000 });
    }
  }
  async start() {
    if (process.platform !== 'win32') throw new Error('本地引擎仅支持 Windows x64');
    if (this.pythonProcess && this.pythonProcess.exitCode === null) return;
    for (const rel of [
      'frontend/index.html', 'backend/src/weiguang_backend/main.py',
      'animation_engine/src/animation_engine/spoken_movie.py',
    ]) if (!fs.existsSync(path.join(this.serviceRoot, rel))) {
      throw new Error('安装包缺少服务源码：' + rel);
    }
    const engine = this.engine();
    const python = executable(engine, 'python.exe');
    executable(engine, 'ffmpeg.exe');
    executable(engine, 'initdb.exe');
    executable(engine, 'pg_ctl.exe');
    const texBin = this.skipTexBootstrap ? path.join(engine, 'Library', 'bin') : await this.ensureTex();
    const env = this.processEnv(texBin);
    this.progress('检查 Windows 数学与视频依赖…');
    await run(python, ['-c', 'import manim, fastapi, psycopg, edge_tts; print("NATIVE_RUNTIME_READY")'],
      { env, timeout: 60000 });
    await this.startPostgres(env);
    this.progress('启动本地视频引擎…');
    this.stopRequested = false;
    this.pythonProcess = spawn(python, [
      '-m', 'uvicorn', 'weiguang_backend.main:create_app', '--factory',
      '--host', HOST, '--port', API_PORT,
    ], { cwd: this.backendCwd(), env, windowsHide: true, stdio: 'ignore' });
    this.pythonProcess.on('error', () => {
      if (!this.stopRequested) this.progress('Windows 后端进程启动失败');
    });
    this.pythonProcess.on('exit', code => {
      if (!this.stopRequested) this.progress('后端已退出（退出代码 ' + code + '）');
    });
  }
  async stop() {
    this.stopRequested = true;
    if (this.pythonProcess && this.pythonProcess.exitCode === null) this.pythonProcess.kill();
    this.pythonProcess = null;
    if (this.startedPostgres) {
      this.startedPostgres = false;
      try {
        await run(executable(this.engine(), 'pg_ctl.exe'),
          ['-D', this.postgresDirectory(), '-m', 'fast', '-w', 'stop'],
          { env: this.processEnv(''), timeout: 30000 });
      } catch { /* retain the database directory and never destroy data */ }
    }
  }
}
module.exports = { NativeServices, executable, latexCommand, texLayout, texInstallerArgs };
