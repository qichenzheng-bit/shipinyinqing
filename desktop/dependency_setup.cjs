'use strict';
/* Trusted Windows-only dependency bootstrap for the installed desktop app.
 * The local signed/pinned installer script owns all download endpoints.
 * No renderer-provided commands, URLs, installer arguments or PowerShell text.
 */
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');

const MODES=Object.freeze(['Check','Install']);
const START_TAG='WEIGUANG_DEPENDENCIES ';
function dependencyScript({packaged=false,resourcesPath='',directory=__dirname}={}){
  const file=packaged
    ?path.join(resourcesPath,'setup-dependencies.ps1')
    :path.join(directory,'setup-dependencies.ps1');
  if(!fs.existsSync(file))throw new Error('DEPENDENCY_SETUP_SCRIPT_MISSING');
  return file;
}
function localPaths({env=process.env,exists=fs.existsSync,read=fs.readdirSync}={}){
  const local=env.LOCALAPPDATA||path.join(os.homedir(),'AppData','Local');
  const home=path.join(local,'WeiGuangMath');
  const runtime=path.join(home,'runtimes');
  const roots=[path.join(runtime,'node')];
  try{
    for(const name of read(runtime)){
      if(/^node-v\d+\.\d+\.\d+$/.test(name))roots.push(path.join(runtime,name));
    }
  }catch{}
  // Include versioned fallback runtimes, newest first, no DLL or arbitrary paths.
  const versioned=roots.slice(1).sort((a,b)=>b.localeCompare(a,undefined,{numeric:true}));
  const bin=[
    path.join(home,'cli','node_modules','.bin'),
    ...versioned.filter(x=>exists(path.join(x,'node.exe'))),
    ...(exists(path.join(roots[0],'node.exe'))?[roots[0]]:[]),
    path.join(local,'Programs','DockerDesktop','resources','bin'),
    path.join(env.ProgramFiles||'C:\\Program Files','Docker','Docker','resources','bin'),
    path.join(env.ProgramFiles||'C:\\Program Files','nodejs'),
  ];
  return bin;
}
function withLocalTools(env=process.env,opts={}){
  const clone={...env};
  const prior=env.Path||env.PATH||'';
  const dirs=localPaths({env,...opts});
  const value=[...dirs,prior].filter(Boolean).join(path.delimiter);
  // Windows is case-insensitive: don't pass two conflicting PATH keys.
  for(const name of Object.keys(clone))if(name.toLowerCase()==='path')delete clone[name];
  clone.Path=value;
  return clone;
}
function parseCheck(stdout){
  const line=String(stdout).split(/\r?\n/).find(x=>x.startsWith(START_TAG));
  if(!line)throw new Error('DEPENDENCY_CHECK_UNAVAILABLE');
  let value;
  try{value=JSON.parse(line.slice(START_TAG.length));}catch{throw new Error('DEPENDENCY_CHECK_INVALID_JSON');}
  if(!value || value.schema_version!==1||
      !['wsl','docker','node','ai_clis'].every(k=>typeof value[k]==='boolean'))
    throw new Error('DEPENDENCY_CHECK_INVALID_RESPONSE');
  return value;
}
function runSetup({mode='Check',onProgress=()=>{},runner=spawn,
                   script=dependencyScript(),timeoutMs=30*60*1000,
                   platform=process.platform}={}){
  if(platform!=='win32')return Promise.reject(new Error('WINDOWS_DEPENDENCIES_ONLY'));
  if(!MODES.includes(mode))return Promise.reject(new Error('INVALID_DEPENDENCY_INSTALL_MODE'));
  return new Promise((resolve,reject)=>{
    const args=['-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
      '-File',script,'-Mode',mode];
    const child=runner('powershell.exe',args,{
      windowsHide:true,stdio:['ignore','pipe','pipe'],
      env:withLocalTools(process.env),
    });
    if(!child || !child.stdout || !child.stderr) {
      reject(new Error('DEPENDENCY_SETUP_PROCESS_INVALID'));return;
    }
    let buffer='',all='',settled=false;
    const done=(err,result)=>{
      if(settled)return;
      settled=true;clearTimeout(timer);
      if(err)reject(err);else resolve(result);
    };
    const timer=setTimeout(()=>{
      child.kill();done(new Error('DEPENDENCY_SETUP_TIMEOUT'));
    },timeoutMs);
    const receive=data=>{
      all+=data.toString('utf8');
      if(all.length>150000){child.kill();done(new Error('DEPENDENCY_SETUP_LOG_OVERFLOW'));return;}
      const lines=(buffer+data.toString('utf8')).split(/\r?\n/);
      buffer=lines.pop()||'';
      for(const line of lines){
        if(line.startsWith('[WeiGuang] ')){
          const safe=line.slice(11,350);
          // Progress messages are authored in our packaged script only.
          onProgress(safe);
        }
      }
    };
    child.stdout.on('data',receive);
    // Never expose installer stderr: external package managers may log tokens.
    child.stderr.on('data',()=>{});
    child.on('error',()=>done(new Error('DEPENDENCY_SETUP_POWERSHELL_MISSING')));
    child.on('close',code=>{
      if(mode==='Check'){
        try{if(code!==0)throw Error('DEPENDENCY_CHECK_FAILED');
          done(null,{code,status:parseCheck(all)});
        }catch(err){done(err);}
      }else if(code===0 || code===3010){
        done(null,{code,needs_reboot:code===3010});
      }else done(new Error('DEPENDENCY_SETUP_FAILED_RETRY_FROM_APP'));
    });
  });
}
module.exports={dependencyScript,localPaths,withLocalTools,parseCheck,runSetup};
