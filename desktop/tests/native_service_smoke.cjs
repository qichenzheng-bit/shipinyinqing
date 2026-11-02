'use strict';
/* Real Windows CI smoke: initialize packaged PostgreSQL, Python API and TeX.
   Uses only disposable RUNNER_TEMP storage; never touches customer data. */
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
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
    if(!healthy)throw new Error('NATIVE_WINDOWS_BACKEND_DID_NOT_START');
    if(!fs.existsSync(path.join(manager.postgresDirectory(),'PG_VERSION')))
      throw new Error('NATIVE_POSTGRESQL_CLUSTER_MISSING');
    if (manager.postgresDirectory().includes('微光数学'))
      throw new Error('POSTGRESQL_CLUSTER_ROOT_STILL_LOCALIZED');
    console.log('NATIVE_WINDOWS_API_POSTGRESQL_MIKTEX_COMPILE_SMOKE_PASSED');
  }finally{await manager.stop();}
})().catch(e=>{console.error(e);process.exitCode=1;});
