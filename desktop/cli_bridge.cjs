'use strict';
/* Windows local-only CLI worker: no HTTP listener, no shell command from model. */
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const PROVIDERS=Object.freeze({
  codex_cli:'codex',gemini_cli:'gemini',codebuddy_cli:'codebuddy',
});
const EFFORTS=Object.freeze({
  codex_cli:['default','low','medium','high','xhigh','max'],
  gemini_cli:['default','low','medium','high'],
  codebuddy_cli:['default','minimal','low','medium','high','xhigh','max'],
});
const MODEL_ID=/^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,199}$/;
const MAX_STDOUT=2200000;

function validateTask(task){
  if(!task || !Object.hasOwn(PROVIDERS,task.provider) ||
      typeof task.model_id!=='string' || !MODEL_ID.test(task.model_id) ||
      !EFFORTS[task.provider].includes(task.reasoning_effort) ||
      !/^[a-f0-9]{32}$/.test(task.id||'') ||
      !/^[a-f0-9]{64}$/.test(task.lease_token||'') ||
      !task.payload || typeof task.payload.system!=='string' ||
      typeof task.payload.user_json!=='string'){
    throw new Error('CLI_REQUEST_VALIDATION_FAILED');
  }
  if(task.payload.system.length+task.payload.user_json.length>200000)
    throw new Error('CLI_REQUEST_TOO_LARGE');
  return task;
}

function unwrapJson(raw){
  if(typeof raw!=='string'||raw.length>MAX_STDOUT)throw new Error('CLI_OUTPUT_INVALID');
  let text=raw.trim();
  if(text.startsWith('')){ /* no-op; retained for pure helper tests */ }
  if(text.startsWith('```')){
    text=text.replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'').trim();
  }
  let value;
  try{value=JSON.parse(text);}catch{throw new Error('CLI_RESPONSE_NOT_JSON');}
  if(!value||typeof value!=='object'||Array.isArray(value))
    throw new Error('CLI_RESPONSE_NOT_JSON_OBJECT');
  const nested=value.response??value.result??value.output_text;
  if(typeof nested==='string')return unwrapJson(nested);
  if(nested&&typeof nested==='object'&&!Array.isArray(nested))return nested;
  return value;
}

function reasoningGemini(model,effort){
  if(effort==='default')return null;
  if(model.startsWith('gemini-3'))
    return {thinkingLevel:{low:'low',medium:'medium',high:'high'}[effort]};
  if(model.startsWith('gemini-2.5'))
    return {thinkingBudget:{low:1024,medium:8192,high:24576}[effort]};
  throw new Error('GEMINI_MODEL_THINKING_CONTROLS_NOT_KNOWN');
}

function commandFor(task,tmpdir){
  validateTask(task);
  const model=task.model_id,effort=task.reasoning_effort;
  let args=[],output=null,extraEnv={};
  if(task.provider==='codex_cli'){
    output=path.join(tmpdir,'last-message.json');
    args=['exec','--ephemeral','--skip-git-repo-check',
      '--sandbox','read-only','--model',model,
      '--output-last-message',output];
    if(effort!=='default')args.push('-c','model_reasoning_effort="'+effort+'"');
    args.push('-'); // stdin only: never interpolate user prompt in a command
  }else if(task.provider==='gemini_cli'){
    args=['--model',model,'--output-format','json','--approval-mode','plan',
      '--prompt','Return JSON for the piped teaching request. Do not call tools.'];
    const thinking=reasoningGemini(model,effort);
    if(thinking){
      const file=path.join(tmpdir,'gemini-system-settings.json');
      fs.writeFileSync(file,JSON.stringify({modelConfigs:{overrides:[
        {match:{model},modelConfig:{generateContentConfig:{thinkingConfig:thinking}}}
      ]}}),{mode:0o600});
      extraEnv.GEMINI_CLI_SYSTEM_SETTINGS_PATH=file;
    }
  }else{
    args=['--model',model,'--output-format','json',
      '--permission-mode','plan','-p',
      'Return ONLY JSON for the piped teaching request; do not use tools.'];
    if(effort!=='default')args.push('--settings',JSON.stringify({reasoningEffort:effort}));
  }
  return {command:PROVIDERS[task.provider],args,output,extraEnv};
}

function runProcess(command,args,{cwd,env,stdin='',timeoutMs=215000}={}){
  return new Promise((resolve,reject)=>{
    // npm-installed CLIs can be .cmd wrappers on Windows. User text is on
    // stdin only. Model IDs have a strict safe alphabet; all other args fixed.
    const child=spawn(command,args,{cwd,
      env:{...process.env,NO_COLOR:'1',...env},
      windowsHide:true,shell:process.platform==='win32',
      stdio:['pipe','pipe','pipe']});
    let stdout='',settled=false;
    const done=(err,value)=>{
      if(settled)return;
      settled=true;clearTimeout(timer);
      if(err)reject(err);else resolve(value);
    };
    const timer=setTimeout(()=>{
      child.kill();done(new Error('CLI_PROCESS_TIMEOUT'));
    },timeoutMs);
    child.on('error',()=>done(new Error('CLI_BINARY_NOT_INSTALLED')));
    child.stdout.on('data',d=>{
      stdout+=d.toString('utf8');
      if(stdout.length>MAX_STDOUT){
        child.kill();done(new Error('CLI_OUTPUT_TOO_LARGE'));
      }
    });
    // never record stderr or prompts; they may contain account secrets
    child.stderr.on('data',()=>{});
    child.on('close',code=>code!==0
      ?done(new Error('CLI_PROCESS_FAILED_OR_LOGIN_REQUIRED'))
      :done(null,{stdout}));
    child.stdin.on('error',()=>{});
    child.stdin.end(stdin);
  });
}

async function executeTask(task,executor=runProcess){
  validateTask(task);
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'weiguang-cli-'));
  try{
    const spec=commandFor(task,dir);
    const prompt=[task.payload.system,
      'Do not access files, run commands or invoke tools.',
      'INPUT JSON:',task.payload.user_json].join('\n\n');
    const p=await executor(spec.command,spec.args,{
      cwd:dir,stdin:prompt,env:spec.extraEnv});
    const raw=spec.output&&fs.existsSync(spec.output)
      ?fs.readFileSync(spec.output,'utf8'):p.stdout;
    return unwrapJson(raw);
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
}

async function detectVersions(executor=runProcess){
  const versions={};
  for(const [key,cmd] of Object.entries(PROVIDERS)){
    try{
      const found=await executor(cmd,['--version'],{timeoutMs:6000});
      if(typeof found.stdout==='string'&&found.stdout.trim())
        versions[key]=found.stdout.trim().slice(0,100);
    }catch{}
  }
  return versions;
}

function createBridge({origin,authToken,bridgeToken,
                       executor=executeTask,detect=detectVersions,http=fetch}={}){
  if(origin!=='http://127.0.0.1:8000'||!authToken||!bridgeToken)
    throw new Error('CLI_BRIDGE_REQUIRES_LOCAL_AUTHENTICATED_BACKEND');
  let stopped=false,busy=false,pulse=0,poll=0;
  const headers={'Content-Type':'application/json',
    'X-API-Key':authToken,'X-CLI-Bridge-Token':bridgeToken};
  const request=async(suffix,method='GET',body)=>{
    const response=await http(origin+'/api/v1/ai/cli/'+suffix,{
      method,headers,redirect:'error',signal:AbortSignal.timeout(6000),
      ...(body===undefined?{}:{body:JSON.stringify(body)}),
    });
    if(!response.ok)throw new Error('CLI_BRIDGE_BACKEND_UNAVAILABLE');
    return response.json();
  };
  async function heartbeat(){
    if(stopped)return;
    const versions=await detect();
    if(!stopped)await request('heartbeat','POST',{versions});
  }
  async function tick(){
    if(busy||stopped)return;
    busy=true;
    try{
      const {task}=await request('next');
      if(!task||stopped)return;
      let result;
      try{result={output:await executor(task)};}
      catch(err){
        const msg=String(err&&err.message||'CLI_PROCESS_FAILED');
        result={error:/^[A-Z0-9_]{3,120}$/.test(msg)?msg:'CLI_PROCESS_FAILED'};
      }
      if(!stopped)await request('result','POST',{
        id:task.id,lease_token:task.lease_token,...result});
    }catch{}finally{busy=false;}
  }
  function start(){
    heartbeat().catch(()=>{});tick().catch(()=>{});
    pulse=setInterval(()=>heartbeat().catch(()=>{}),12000);
    poll=setInterval(()=>tick().catch(()=>{}),1100);
  }
  function stop(){
    stopped=true;clearInterval(pulse);clearInterval(poll);
  }
  return {start,stop,heartbeat,tick};
}

module.exports={createBridge,executeTask,commandFor,unwrapJson,
  validateTask,reasoningGemini,detectVersions,runProcess};
