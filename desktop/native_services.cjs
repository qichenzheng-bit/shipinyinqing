'use strict';
/**
 * Windows-only local production runtime. No Docker daemon, WSL2 or Redis.
 * The installer carries a CPython/Manim/FFmpeg/PostgreSQL environment and a
 * verified MiKTeX portable installer. Mutable data stays in Electron userData.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
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
async function run(exe, args, options = {}) {
  return exec(exe, args, {
    timeout: options.timeout || 120000, windowsHide: true,
    cwd: options.cwd, env: options.env, maxBuffer: 2 * 1024 * 1024,
  });
}
class NativeServices {
  constructor({ serviceRoot, runtimeRoot, userDir, secrets, progress = () => {} }) {
    this.serviceRoot = serviceRoot;
    this.runtimeRoot = runtimeRoot;
    this.userDir = userDir;
    this.secrets = secrets;
    this.progress = progress;
    this.pythonProcess = null;
    this.startedPostgres = false;
    this.stopRequested = false;
  }
  engine() { return path.join(this.runtimeRoot, 'engine'); }
  async ensureTex() {
    const dest = path.join(this.userDir, 'tex-runtime');
    fs.mkdirSync(dest, { recursive: true });
    let latex = latexCommand(dest);
    if (!latex) {
      const installer = path.join(this.runtimeRoot, 'basic-miktex-25.12-x64.exe');
      if (!fs.existsSync(installer)) throw new Error('安装包缺少 MiKTeX 公式运行时。');
      this.progress('首次启动：自动配置 LaTeX 公式组件…');
      await run(installer, [
        '--private', '--unattended', '--package-set=basic',
        '--user-install=' + dest,
        '--user-config=' + path.join(dest, 'config'),
        '--user-data=' + path.join(dest, 'data'),
      ], { cwd: dest, timeout: 20 * 60 * 1000 });
      latex = latexCommand(dest);
      if (!latex) throw new Error('MiKTeX 自动安装未完成，无法验证 latex.exe。');
    }
    return path.dirname(latex);
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
    return {
      ...process.env,
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
  async startPostgres(env) {
    const engine = this.engine();
    const pgctl = executable(engine, 'pg_ctl.exe');
    const pgdir = path.join(this.userDir, 'postgresql17');
    const logfile = path.join(this.userDir, 'postgresql.log');
    fs.mkdirSync(this.userDir, { recursive: true });
    if (!fs.existsSync(path.join(pgdir, 'PG_VERSION'))) {
      if (fs.existsSync(pgdir) && fs.readdirSync(pgdir).length) {
        throw new Error('PostgreSQL 数据目录存在未完成的初始化，已保留原始数据，请先备份检查。');
      }
      this.progress('初始化本地 PostgreSQL 17 数据库…');
      const passfile = path.join(this.userDir, 'initdb-' + crypto.randomBytes(8).toString('hex') + '.tmp');
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
    const texBin = await this.ensureTex();
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
    ], { cwd: this.userDir, env, windowsHide: true, stdio: 'ignore' });
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
          ['-D', path.join(this.userDir, 'postgresql17'), '-m', 'fast', '-w', 'stop'],
          { env: this.processEnv(''), timeout: 30000 });
      } catch { /* retain the database directory and never destroy data */ }
    }
  }
}
module.exports = { NativeServices, executable, latexCommand };
