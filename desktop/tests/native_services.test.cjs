'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { NativeServices, texLayout, texInstallerArgs } = require('../native_services.cjs');

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'weiguang-tex-test-'));
  const runtimeRoot = path.join(root, 'runtime');
  const userDir = path.join(root, 'user', '微光数学', 'native-services');
  fs.mkdirSync(runtimeRoot, {recursive:true});
  fs.mkdirSync(userDir, {recursive:true});
  fs.writeFileSync(path.join(runtimeRoot, 'basic-miktex-25.12-x64.exe'), 'stub');
  return {root,runtimeRoot,userDir};
}
function latexAt(root) {
  const latex = path.join(root, 'miktex', 'bin', 'x64', 'latex.exe');
  fs.mkdirSync(path.dirname(latex), {recursive:true});
  fs.writeFileSync(latex,'fixture');
  return latex;
}
function mockRunner(calls, { failInstall=false, failCompile=false } = {}) {
  return async (executable,args,options) => {
    calls.push({executable,args,options});
    if (path.basename(executable).startsWith('basic-miktex-')) {
      if (failInstall) throw Error('simulated installer failure');
      const installArg=args.find(x=>x.startsWith('--user-install='));
      assert.ok(installArg);
      latexAt(installArg.slice('--user-install='.length));
    } else if (path.basename(executable).toLowerCase()==='latex.exe') {
      assert.ok(args.includes('probe.tex'));
      assert.ok(args.includes('-halt-on-error'));
      if (failCompile) throw Error('simulated latex compilation failure');
      fs.writeFileSync(path.join(options.cwd,'probe.dvi'),'compiled');
    } else {
      throw Error('unexpected command ' + executable);
    }
  };
}
function manager(f, calls, opts={}) {
  return new NativeServices({
    serviceRoot:f.root,runtimeRoot:f.runtimeRoot,userDir:f.userDir,
    secrets:{},texRunner:mockRunner(calls,opts),
  });
}
test('three MiKTeX roots are distinct siblings, not parent and child',()=>{
  const roots=texLayout(path.join(os.tmpdir(),'微光数学'),2);
  const args=texInstallerArgs(roots);
  const dirs=args.filter(x=>x.startsWith('--user-')).map(x=>x.split('=').slice(1).join('='));
  assert.equal(dirs.length,3);
  for (const a of dirs) for (const b of dirs) if (a!==b) {
    assert.ok(path.relative(a,b).startsWith('..'));
  }
  assert.throws(()=>texInstallerArgs({
    install:roots.base, config:path.join(roots.base,'config'),data:roots.data,
  }),/OVERLAP/);
});
test('legacy nested config is preserved; first install is isolated and second is reused',async()=>{
  const f=fixture(), calls=[];
  try {
    const legacy=path.join(f.userDir,'tex-runtime');
    const config=path.join(legacy,'config');
    fs.mkdirSync(config,{recursive:true});
    fs.writeFileSync(path.join(config,'existing.ini'),'do-not-delete');
    const service=manager(f,calls);
    const first=await service.ensureTex();
    const again=await service.ensureTex();
    assert.equal(first,again);
    assert.ok(first.includes('tex-runtime-v2'));
    assert.equal(calls.filter(x=>path.basename(x.executable).startsWith('basic-miktex-')).length,1);
    assert.equal(fs.readFileSync(path.join(config,'existing.ini'),'utf8'),'do-not-delete');
  } finally { fs.rmSync(f.root,{recursive:true,force:true}); }
});
test('a valid previously installed legacy TeX is reused without another installer',async()=>{
  const f=fixture(),calls=[];
  try {
    const legacy=path.join(f.userDir,'tex-runtime');
    const latex=latexAt(legacy);
    fs.rmSync(path.join(f.runtimeRoot,'basic-miktex-25.12-x64.exe'));
    const result=await manager(f,calls).ensureTex();
    assert.equal(result,path.dirname(latex));
    assert.equal(calls.length,1);
    assert.equal(path.basename(calls[0].executable),'latex.exe');
  } finally { fs.rmSync(f.root,{recursive:true,force:true}); }
});
test('incomplete v2 root is untouched and repair installs to the clean v3 slot',async()=>{
  const f=fixture(),calls=[];
  try {
    const old=texLayout(f.userDir,2);
    fs.mkdirSync(old.config,{recursive:true});
    fs.writeFileSync(path.join(old.config,'partial.ini'),'keep');
    const dest=await manager(f,calls).ensureTex();
    assert.ok(dest.includes('tex-runtime-v3'));
    assert.equal(fs.readFileSync(path.join(old.config,'partial.ini'),'utf8'),'keep');
  } finally { fs.rmSync(f.root,{recursive:true,force:true}); }
});
test('failed installer is reported, not treated as ready or retried in a loop',async()=>{
  const f=fixture(),calls=[];
  try {
    await assert.rejects(manager(f,calls,{failInstall:true}).ensureTex(),/MiKTeX 初始化未成功/);
    assert.equal(calls.filter(x=>path.basename(x.executable).startsWith('basic-miktex-')).length,1);
  } finally { fs.rmSync(f.root,{recursive:true,force:true}); }
});

test('failed compilation from an existing TeX binary never causes another long install',async()=>{
  const f=fixture(),calls=[];
  try {
    latexAt(texLayout(f.userDir,2).install);
    await assert.rejects(manager(f,calls,{failCompile:true}).ensureTex(),/停止重复安装/);
    assert.equal(calls.filter(x=>path.basename(x.executable).startsWith('basic-miktex-')).length,0);
  } finally { fs.rmSync(f.root,{recursive:true,force:true}); }
});
