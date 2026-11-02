'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os');
const {validateTask,commandFor,unwrapJson,reasoningGemini,executeTask,createBridge}
  =require('../cli_bridge.cjs');
function task(provider='codex_cli',model_id='gpt-6.1-sol',reasoning_effort='high'){
  return {provider,model_id,reasoning_effort,id:'a'.repeat(32),
    lease_token:'b'.repeat(64),
    payload:{system:'Generate math lesson JSON',user_json:'{"problem":"x^2"}'}};
}
test('no dynamic command or untrusted model arguments',()=>{
  for(const provider of ['powershell','../shell','workbuddy'])
    assert.throws(()=>validateTask({...task(),provider}),/VALIDATION/);
  for(const model_id of ['a && del c:', '$(rm -rf /)','x" && echo injected',''])
    assert.throws(()=>validateTask({...task(),model_id}),/VALIDATION/);
  assert.throws(()=>validateTask({...task(),reasoning_effort:'delete'}),/VALIDATION/);
});
test('Codex chosen model and reasoning are read-only, prompt through stdin',()=>{
  const spec=commandFor(task(),'/tmp/wgtest');
  assert.equal(spec.command,'codex');
  assert.ok(spec.args.includes('read-only'));
  assert.ok(spec.args.includes('gpt-6.1-sol'));
  assert.ok(spec.args.includes('model_reasoning_effort="high"'));
  assert.equal(spec.args.at(-1),'-');
  assert.ok(!spec.args.join(' ').includes('x^2'));
});
test('Gemini 3/2.5 thinking mappings and CLI sandbox',()=>{
  assert.deepEqual(reasoningGemini('gemini-3.1-pro','high'),{thinkingLevel:'high'});
  assert.deepEqual(reasoningGemini('gemini-2.5-pro','medium'),{thinkingBudget:8192});
  assert.throws(()=>reasoningGemini('unsupported','high'),/NOT_KNOWN/);
  const dir=fs.mkdtempSync(os.tmpdir()+'/wg-config-');
  try{
    const spec=commandFor(task('gemini_cli','gemini-3.1-pro','low'),dir);
    assert.ok(spec.args.includes('plan'));
    const cfg=JSON.parse(fs.readFileSync(spec.extraEnv.GEMINI_CLI_SYSTEM_SETTINGS_PATH,'utf8'));
    assert.equal(cfg.modelConfigs.overrides[0].modelConfig.generateContentConfig.thinkingConfig.thinkingLevel,'low');
  }finally{fs.rmSync(dir,{force:true,recursive:true});}
});
test('CodeBuddy is CLI, not unverified WorkBuddy desktop API',()=>{
  const spec=commandFor(task('codebuddy_cli','reasoning','xhigh'),'/tmp/wgtest');
  assert.equal(spec.command,'codebuddy');
  assert.ok(spec.args.includes('plan'));
  assert.ok(spec.args.includes('{"reasoningEffort":"xhigh"}'));
  assert.ok(!spec.args.join(' ').includes('x^2'));
});
test('CLI JSON format is strict and handles known wrappers',()=>{
  assert.deepEqual(unwrapJson('{"ok":true}'),{ok:true});
  assert.deepEqual(unwrapJson('{"response":"{\\"ok\\":true}"}'),{ok:true});
  assert.deepEqual(unwrapJson('```json\n{"ok":true}\n```'),{ok:true});
  assert.throws(()=>unwrapJson('execute files'),/NOT_JSON/);
  assert.throws(()=>unwrapJson('[1,2]'),/OBJECT/);
});
test('Codex writes only ephemeral output; prompt is never CLI argv',async()=>{
  const result=await executeTask(task(),async(cmd,args,opts)=>{
    assert.equal(cmd,'codex');
    assert.ok(opts.stdin.includes('x^2'));
    assert.ok(!args.includes(opts.stdin));
    assert.ok(opts.cwd.includes('weiguang-cli-'));
    fs.writeFileSync(args[args.indexOf('--output-last-message')+1],'{"lesson":"ready"}');
    return {stdout:'transport not JSON'};
  });
  assert.deepEqual(result,{lesson:'ready'});
});
test('backend polling requires local origin and two independent secrets',async()=>{
  const calls=[];
  const http=async(url,opts)=>{
    assert.ok(url.startsWith('http://127.0.0.1:8000/api/v1/ai/cli/'));
    assert.equal(opts.headers['X-API-Key'],'api-secret');
    assert.equal(opts.headers['X-CLI-Bridge-Token'],'bridge-secret');
    calls.push(url);
    return {ok:true,json:async()=>url.endsWith('/next')?{task:task()}:{ok:true}};
  };
  const worker=createBridge({origin:'http://127.0.0.1:8000',
    authToken:'api-secret',bridgeToken:'bridge-secret',http,
    detect:async()=>({codex_cli:'installed'}),
    executor:async()=>({ok:true})});
  await worker.heartbeat();await worker.tick();worker.stop();
  assert.ok(calls.some(x=>x.endsWith('/result')));
  assert.throws(()=>createBridge({origin:'https://evil',authToken:'a',bridgeToken:'b'}),/LOCAL/);
});
