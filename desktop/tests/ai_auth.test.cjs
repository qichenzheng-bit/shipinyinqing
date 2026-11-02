'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const a=require('../ai_auth.cjs');
test('only three allowlisted CLI providers; no WorkBuddy',()=>{
  assert.deepEqual(Object.keys(a.COMMANDS),['codex_cli','gemini_cli','codebuddy_cli']);
  for(const input of ['workbuddy','workbuddy_cli','powershell','../codebuddy','','codex_cli && echo bad'])
    assert.throws(()=>a.vendor(input),/UNSUPPORTED_CLI_PROVIDER/);
});
test('login launches only an exact vendor CLI in separate Windows console',async()=>{
  let invocation,unref=false;
  const result=await a.login('gemini_cli',{platform:'win32',check:async()=>true,
    launch:(cmd,args,opts)=>{invocation={cmd,args,opts};
      return {pid:123,unref:()=>{unref=true;}};}});
  assert.equal(result.authentication,'pending');
  assert.deepEqual(invocation.args,['/d','/k','gemini']);
  assert.equal(invocation.cmd,'cmd.exe');
  assert.equal(invocation.opts.windowsHide,false);
  assert.ok(unref);
  await assert.rejects(a.login('codex_cli',{platform:'win32',check:async()=>false}),
    /CLI_NOT_INSTALLED/);
  await assert.rejects(a.login('codex_cli',{platform:'linux',check:async()=>true}),
    /WINDOWS_DESKTOP_REQUIRED/);
});
test('model dropdown choices are safe and custom CodeBuddy models expose no secrets',()=>{
  const custom={models:[{id:'deepseek-r1',apiKey:'SECRET'}],
    availableModels:['glm-4.7','bad \"; rm -rf /','sonnet']};
  const result=a.models('codebuddy_cli',{read:()=>JSON.stringify(custom)});
  assert.ok(result.some(x=>x.id==='deepseek-r1'));
  assert.ok(result.some(x=>x.id==='glm-4.7'));
  assert.equal(JSON.stringify(result).includes('SECRET'),false);
  assert.equal(JSON.stringify(result).includes('rm -rf'),false);
});
test('status never treats an installed Gemini or CodeBuddy as authenticated',async()=>{
  assert.deepEqual(await a.status('gemini_cli',{check:async()=>true}),
    {installed:true,authentication:'unverified'});
  assert.deepEqual(await a.status('codebuddy_cli',{check:async()=>false}),
    {installed:false,authentication:'unavailable'});
});
