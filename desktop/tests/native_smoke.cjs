'use strict';
/* Launch Electron itself, inspect real native window and screenshot both modes.
   No Docker, API key, model or full video rendering is invoked. */
const fs=require('node:fs');
const path=require('node:path');
const { _electron: electron }=require('playwright-core');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const app=await electron.launch({
    args:['.'],cwd:root,
    timeout:45000,
  });
  try{
    const win=await app.firstWindow();
    await win.getByRole('heading',{name:'微光数学'}).waitFor();
    await win.getByRole('button',{name:'启动并进入工作台'}).waitFor();
    const snapshot=path.join(root,'screenshots');
    fs.mkdirSync(snapshot,{recursive:true});
    await win.screenshot({path:path.join(snapshot,'03-electron-native-local.png')});
    await win.getByRole('tab',{name:'连接服务器'}).click();
    await win.getByRole('button',{name:'连接服务器',exact:true}).waitFor();
    await win.getByLabel('服务器 HTTPS 地址').fill('https://math.example.com');
    await win.screenshot({path:path.join(snapshot,'04-electron-native-server.png')});
    console.log('NATIVE_ELECTRON_WINDOW_ACCEPTED');
  } finally{
    await app.close();
  }
})().catch(error=>{
  console.error(error);
  process.exitCode=1;
});
