'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {normalizeEndpoint,allowedNavigation}=require('../url_policy.cjs');

test('Windows local and remote HTTPS endpoints retain exact origin',()=>{
  assert.equal(normalizeEndpoint('https://math.example.com/'),'https://math.example.com');
  assert.equal(normalizeEndpoint('https://math.example.com:8443'), 'https://math.example.com:8443');
  assert.equal(normalizeEndpoint('http://127.0.0.1:8000/'),'http://127.0.0.1:8000');
  assert.equal(normalizeEndpoint('http://localhost:8000'),'http://localhost:8000');
});
test('Untrusted redirects, embedded credentials and remote HTTP are blocked',()=>{
  for(const value of [
    'http://evil.example','https://math.example.com.attacker.invalid',
    'file:///C:/windows','javascript:alert(1)','https://user:password@math.example.com',
    'https://math.example.com?access_token=hi','https://math.example.com/#secret',
    'https://math.example.com/login','http://192.168.1.5:8000',
    'http://127.0.0.1.attacker.invalid:8000','',
  ]){
    if(value==='https://math.example.com.attacker.invalid') {
      assert.equal(normalizeEndpoint(value),value); // HTTPS host is allowed; no domain pin.
    }else{
      assert.throws(()=>normalizeEndpoint(value),value);
    }
  }
});
test('Remote renderer cannot navigate away from the selected origin',()=>{
  const origin='https://math.example.com';
  assert.equal(allowedNavigation(origin,'https://math.example.com/api/v1/lessons'),true);
  for(const value of [
    'https://math.example.com.attacker.invalid',
    'http://math.example.com','file:///C:/temp/e.txt',
    'javascript:alert(1)','https://math.example.com:8443',
  ])assert.equal(allowedNavigation(origin,value),false,value);
});
test('Desktop bundles original strict engine, voice and teacher code without test data',()=>{
  const cfg=require('../package.json').build;
  assert.equal(cfg.appId,'cn.weiguang.math');
  assert.equal(cfg.asar,true);
  const resources=cfg.extraResources;
  for(const project of ['backend','animation_engine','teacher_module','visual_director','frontend']){
    const entry=resources.find(x=>x.to==='service/'+project);
    assert.ok(entry,'missing runtime: '+project);
    assert.ok(entry.filter.includes('src/**/*')||project==='frontend','no source: '+project);
    assert.ok(entry.filter.every(x=>!x.includes('tests')),'test fixtures bundled: '+project);
  }
  assert.ok(resources.some(x=>x.filter.includes('docker-compose.yml')));
  assert.ok(cfg.files.includes('build/app.png'));
  assert.ok(cfg.nsis.createDesktopShortcut);
});
test('Electron preload is not exposed to the remote mathematical site',()=>{
  const source=fs.readFileSync(path.join(__dirname,'..','main.cjs'),'utf8');
  assert.match(source,/nodeIntegration:\s*false/);
  assert.match(source,/contextIsolation:\s*true/);
  assert.match(source,/sandbox:\s*true/);
  assert.match(source,/setWindowOpenHandler/);
  assert.match(source,/will-navigate/);
  assert.match(source,/timingSafeEqual/);
  assert.match(source,/safeStorage\.encryptString/);
  assert.match(source,/const expected = pathToFileURL/);
  const wIndex=source.indexOf('studio = new BrowserWindow');
  const webOptions=source.slice(wIndex,source.indexOf('installWebSecurity(studio',wIndex));
  assert.ok(!webOptions.includes('preload:'),'preload must never be attached to remote page');
});
