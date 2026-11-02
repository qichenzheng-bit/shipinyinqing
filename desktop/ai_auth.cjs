'use strict';
/* Local Windows account authorization is owned by the vendor CLI, never our site.
 * No OAuth tokens, password fields, or embedded third-party login pages.
 */
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn,execFile}=require('node:child_process');

const COMMANDS=Object.freeze({
  codex_cli:Object.freeze({binary:'codex',login:'codex login',
    message:'已启动 Codex 官方登录。请在自动打开的浏览器完成 ChatGPT 授权。'}),
  gemini_cli:Object.freeze({binary:'gemini',login:'gemini',
    message:'已启动 Gemini 官方登录。首次使用请在向导中选择 Google 账号，随后在浏览器授权。'}),
  codebuddy_cli:Object.freeze({binary:'codebuddy',login:'codebuddy',
    message:'已启动 CodeBuddy 官方登录。首次使用请在向导中选择国内站、国际站或企业站，随后在浏览器授权。'}),
});
// Examples for the dropdown, not a claim that every account can use every model.
const SUGGESTIONS=Object.freeze({
  codex_cli:['gpt-6.1-sol','gpt-6.1-terra','gpt-6-astra','gpt-6-luna','gpt-6-sol','gpt-5.6'],
  gemini_cli:['gemini-3.1-pro-preview','gemini-3-pro-preview','gemini-3-flash-preview',
    'gemini-2.5-pro','gemini-2.5-flash','gemini-2.5-flash-lite'],
  codebuddy_cli:['gpt-5','sonnet','opus'],
});
const MODEL_ID=/^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,199}$/;
function vendor(kind){
  if(!Object.hasOwn(COMMANDS,kind))throw new Error('UNSUPPORTED_CLI_PROVIDER');
  return COMMANDS[kind];
}
function models(kind,{home=os.homedir(),read=fs.readFileSync}={}){
  vendor(kind);
  const found=new Set(SUGGESTIONS[kind]);
  if(kind==='codebuddy_cli'){
    try{
      // Read only model IDs and labels. Never read out API keys or account tokens.
      const settings=JSON.parse(read(path.join(home,'.codebuddy','models.json'),'utf8'));
      for(const item of Array.isArray(settings.models)?settings.models:[]){
        if(typeof item.id==='string' && MODEL_ID.test(item.id))found.add(item.id);
      }
      for(const id of Array.isArray(settings.availableModels)?settings.availableModels:[]){
        if(typeof id==='string' && MODEL_ID.test(id))found.add(id);
      }
    }catch{}
  }
  return [...found].filter(x=>MODEL_ID.test(x)).map(id=>({id,label:id}));
}
function installed(kind,{exec=execFile}={}){
  const bin=vendor(kind).binary;
  return new Promise(resolve=>{
    exec(process.platform==='win32'?'where.exe':'which',[bin],
      {windowsHide:true,timeout:6000},(err,_stdout)=>resolve(!err));
  });
}
async function status(kind,{check=installed,exec=execFile}={}){
  const present=await check(kind);
  if(!present)return {installed:false,authentication:'unavailable'};
  if(kind!=='codex_cli')return {installed:true,authentication:'unverified'};
  return new Promise(resolve=>{
    exec('codex',['login','status'],{windowsHide:true,timeout:7500},err=>
      resolve({installed:true,authentication:err?'unverified':'authenticated'}));
  });
}
async function login(kind,{check=installed,launch=spawn,platform=process.platform}={}){
  const item=vendor(kind);
  if(platform!=='win32')throw new Error('WINDOWS_DESKTOP_REQUIRED_FOR_CLI_LOGIN');
  if(!await check(kind))throw new Error('CLI_NOT_INSTALLED_INSTALL_OFFICIAL_CLI_FIRST');
  // Fixed allowlisted commands. No user text, model name, URL, or project input
  // ever enters the Windows command interpreter.
  const child=launch('cmd.exe',['/d','/k',item.login],
    {detached:true,windowsHide:false,stdio:'ignore',cwd:os.homedir()});
  if(!child || !child.pid)throw new Error('CLI_LOGIN_WINDOW_LAUNCH_FAILED');
  child.unref?.();
  return {launched:true,provider:kind,message:item.message,authentication:'pending'};
}
module.exports={COMMANDS,SUGGESTIONS,MODEL_ID,vendor,models,installed,status,login};
