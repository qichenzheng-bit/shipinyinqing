'use strict';
/* Real Windows CI smoke: initialize packaged PostgreSQL, Python API and TeX.
   Uses only disposable RUNNER_TEMP storage; never touches customer data. */
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const execFileAsync = promisify(execFile);
const { NativeServices } = require('../native_services.cjs');
const root = path.resolve(__dirname, '..', '..');
const working = path.join(process.env.RUNNER_TEMP || path.join(root, 'desktop'), '微光数学','native-services');
const secrets = Object.fromEntries([
  'POSTGRES_PASSWORD','WEIGUANG_API_TOKEN','WEIGUANG_CLI_BRIDGE_TOKEN',
  'WEIGUANG_MODEL_MASTER_KEY',
].map(x => [x, crypto.randomBytes(32).toString('hex')]));
secrets.WEIGUANG_MODEL_MASTER_KEY = crypto.randomBytes(32).toString('base64url');
const manager = new NativeServices({
  serviceRoot:root,
  runtimeRoot:path.join(root,'desktop','native_runtime'),
  userDir:working,
  secrets,
  skipTexBootstrap: false,
  progress:message=>console.log('[native]',message),
});
(async()=>{
  if (process.platform!=='win32') throw new Error('WINDOWS_CI_REQUIRED');
  try {
    await manager.start();
    const firstTex = await manager.ensureTex();
    const secondTex = await manager.ensureTex();
    if (firstTex !== secondTex || !fs.existsSync(path.join(firstTex, 'latex.exe')))
      throw new Error('MIKTEX_REUSE_OR_FORMULA_COMPILE_FAILED');
    let healthy=false;
    for(let attempt=0;attempt<80;attempt++){
      try {
        const r=await fetch('http://127.0.0.1:8000/health',{signal:AbortSignal.timeout(1500)});
        if(r.ok){healthy=true;break;}
      }catch{}
      await new Promise(resolve=>setTimeout(resolve,1500));
    }

    // A bare latex.exe probe is insufficient: Manim also needs LaTeX
    // templates, packages, dvisvgm and the SVG-to-mobject conversion path.
    // Validate one real MathTex object using the bundled runtime and TeX.
    const media = fs.mkdtempSync(path.join(os.tmpdir(), 'weiguang-manim-mathtex-'));
    try {
      const script = [
        'from manim import MathTex, tempconfig',
        'import sys',
        "with tempconfig({'media_dir': sys.argv[1]}):",
        '    expression = MathTex(r"\\frac{x^2+1}{x+1}")',
        '    assert expression.submobjects, "MATHTEX_EMPTY_MOBJECT"',
        'print("WINDOWS_MANIM_MATHTEX_SVG_PASSED")',
      ].join('\n');
      const {stdout} = await execFileAsync(path.join(manager.engine(), 'python.exe'),
        ['-c', script, media], {
          env: manager.processEnv(firstTex),
          cwd: working,
          timeout: 240000,
          windowsHide: true,
          maxBuffer: 4 * 1024 * 1024,
        });
      if (!stdout.includes('WINDOWS_MANIM_MATHTEX_SVG_PASSED'))
        throw new Error('NATIVE_MANIM_MATHTEX_NOT_VERIFIED');
    } finally {
      fs.rmSync(media, {recursive:true,force:true});
    }
    if(!healthy)throw new Error('NATIVE_WINDOWS_BACKEND_DID_NOT_START');
    if(!fs.existsSync(path.join(manager.postgresDirectory(),'PG_VERSION')))
      throw new Error('NATIVE_POSTGRESQL_CLUSTER_MISSING');
    if (manager.postgresDirectory().includes('微光数学'))
      throw new Error('POSTGRESQL_CLUSTER_ROOT_STILL_LOCALIZED');
    console.log('NATIVE_WINDOWS_API_POSTGRESQL_MIKTEX_COMPILE_SMOKE_PASSED');
  }finally{await manager.stop();}
})().catch(e=>{console.error(e);process.exitCode=1;});
