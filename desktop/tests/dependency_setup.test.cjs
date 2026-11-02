'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {EventEmitter}=require('node:events');
const {localPaths,withLocalTools,parseCheck,runSetup,dependencyScript}
  =require('../dependency_setup.cjs');

test('installer scripts are real tracked source files and cannot be selected by a web renderer',()=>{
  const script=dependencyScript({packaged:false,directory:path.join(__dirname,'..')});
  assert.ok(fs.existsSync(script));
  const nsis=fs.readFileSync(path.join(__dirname,'..','installer.nsh'),'utf8');
  assert.match(nsis,/Page custom WeiGuangDepsPage/);
  assert.match(nsis,/NSD_CreateCheckbox/);
  assert.match(nsis,/customInstall/);
  assert.match(nsis,/ExecToLog/);
  assert.ok(!nsis.includes('rm -rf'));
  const ps=fs.readFileSync(script,'utf8');
  assert.match(ps,/ValidateSet\('Install','Check','WSLOnly'\)/);
  assert.match(ps,/Get-AuthenticodeSignature/);
  assert.match(ps,/Get-FileHash -Algorithm SHA256/);
  assert.match(ps,/@openai\/codex/);
  assert.match(ps,/@google\/gemini-cli/);
  assert.match(ps,/@tencent-ai\/codebuddy-code/);
  assert.match(ps,/--no-distribution/);
  assert.doesNotMatch(ps,/Invoke-Expression|\|\s*iex\b/i);
});
test('only app-owned dependencies are included in PATH; no overwrite of other paths',()=>{
  const base=fs.mkdtempSync(path.join(os.tmpdir(),'wg-deps-path-'));
  const apps=path.join(base,'WeiGuangMath','runtimes');
  fs.mkdirSync(path.join(apps,'node-v24.1.0'),{recursive:true});
  fs.writeFileSync(path.join(apps,'node-v24.1.0','node.exe'),'fixture');
  try{
    const env={LOCALAPPDATA:base,Path:'C:\\ExistingTools',
      ProgramFiles:'C:\\Program Files',WEIGUANG_API_TOKEN:'secret'};
    const result=withLocalTools(env);
    assert.ok(result.Path.startsWith(path.join(base,'WeiGuangMath','cli')));
    assert.ok(result.Path.includes('node-v24.1.0'));
    assert.ok(result.Path.endsWith('C:\\ExistingTools'));
    assert.equal(result.WEIGUANG_API_TOKEN,'secret'); // This helper only modifies PATH.
    assert.equal(localPaths({env}).some(x=>x.includes('node-v24.1.0')),true);
  }finally{fs.rmSync(base,{force:true,recursive:true});}
});
test('status requires a known schema with all four dependencies',()=>{
  const expected={schema_version:1,windows_build:22631,wsl:true,docker:false,node:true,ai_clis:false};
  assert.deepEqual(parseCheck('WEIGUANG_DEPENDENCIES '+JSON.stringify(expected)),expected);
  assert.throws(()=>parseCheck('ok'),/UNAVAILABLE/);
  assert.throws(()=>parseCheck('WEIGUANG_DEPENDENCIES {"schema_version":1}'),/INVALID_RESPONSE/);
});
test('check/installer command is fixed and cannot invoke arbitrary PowerShell code',async()=>{
  const makeRunner=(code,stdout='')=>(bin,args,opts)=>{
    assert.equal(bin,'powershell.exe');
    assert.ok(args.includes('-File'));
    assert.ok(args.includes('-Mode'));
    assert.equal(opts.windowsHide,true);
    const child=new EventEmitter();
    child.stdout=new EventEmitter();child.stderr=new EventEmitter();
    process.nextTick(()=>{
      if(stdout)child.stdout.emit('data',Buffer.from(stdout));
      child.emit('close',code);
    });
    child.kill=()=>{};
    return child;
  };
  const text='WEIGUANG_DEPENDENCIES {"schema_version":1,"wsl":true,"docker":true,"node":true,"ai_clis":true}\n';
  const value=await runSetup({platform:'win32',mode:'Check',runner:makeRunner(0,text)});
  assert.equal(value.status.docker,true);
  const reboot=await runSetup({platform:'win32',mode:'Install',runner:makeRunner(3010)});
  assert.equal(reboot.needs_reboot,true);
  await assert.rejects(runSetup({platform:'win32',mode:'Install',runner:makeRunner(2)}),
    /RETRY_FROM_APP/);
  await assert.rejects(runSetup({platform:'win32',mode:'wsl --install'}),/INVALID_DEPENDENCY/);
  await assert.rejects(runSetup({platform:'linux'}),/WINDOWS_DEPENDENCIES_ONLY/);
});
