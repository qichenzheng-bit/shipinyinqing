'use strict';
/* Only installed for the verified local video studio, never a remote HTTPS site. */
const {contextBridge,ipcRenderer}=require('electron');
if(window.location.origin==='http://127.0.0.1:8000'){
  contextBridge.exposeInMainWorld('weiGuangAI',Object.freeze({
    login:kind=>ipcRenderer.invoke('wg:ai-login',kind),
    status:kind=>ipcRenderer.invoke('wg:ai-status',kind),
    models:kind=>ipcRenderer.invoke('wg:ai-models',kind),
  }));
}
