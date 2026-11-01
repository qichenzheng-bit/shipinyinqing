'use strict';
const { contextBridge, ipcRenderer } = require('electron');
// Preload is used ONLY by the trusted launcher file, never by the math site.
contextBridge.exposeInMainWorld('weiGuangLauncher', Object.freeze({
  status: () => ipcRenderer.invoke('wg:status'),
  startLocal: () => ipcRenderer.invoke('wg:start-local'),
  connectLocal: () => ipcRenderer.invoke('wg:connect-local'),
  connectRemote: (url) => ipcRenderer.invoke('wg:connect-remote', url),
  openSettings: () => ipcRenderer.invoke('wg:status'),
  onProgress: (listener) => {
    if (typeof listener !== 'function') return;
    ipcRenderer.on('wg:progress', (_event, status) => listener(status));
  }
}));
