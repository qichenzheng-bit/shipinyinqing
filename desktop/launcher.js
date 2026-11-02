'use strict';
const bridge = window.weiGuangLauncher;
const byId = id => document.getElementById(id);
const controls = ['start-local', 'connect-local', 'connect-remote', 'local-tab', 'remote-tab'];
let busy = false;

function report(message, error = false) {
  const status = byId('status');
  status.textContent = message;
  status.classList.toggle('error', !!error);
}
function setBusy(value) {
  busy = value;
  for (const id of controls) byId(id).disabled = value;
}
function show(mode) {
  if (busy) return;
  const local = mode === 'local';
  byId('local-tab').classList.toggle('active',local);
  byId('remote-tab').classList.toggle('active',!local);
  byId('local-tab').setAttribute('aria-selected',String(local));
  byId('remote-tab').setAttribute('aria-selected',String(!local));
  byId('local-panel').classList.toggle('hidden',!local);
  byId('remote-panel').classList.toggle('hidden',local);
  report(local?'可启动本地数学视频引擎':'输入已部署的服务器地址');
}
async function action(callback) {
  if (busy) return;
  setBusy(true);
  try {
    const result = await callback();
    if (!result || !result.ok) report(result?.error||'无法连接服务',true);
    else report('工作台已打开');
  } catch (error) {
    report(error.message||'启动失败',true);
  } finally {
    setBusy(false);
  }
}

byId('local-tab').addEventListener('click',()=>show('local'));
byId('remote-tab').addEventListener('click',()=>show('remote'));
byId('start-local').addEventListener('click',()=>action(()=>bridge.startLocal()));
byId('connect-local').addEventListener('click',()=>action(()=>bridge.connectLocal()));
byId('connect-remote').addEventListener('click',()=>{
  const url=byId('server-url').value.trim();
  if (!url) return report('请填写服务器地址',true);
  action(()=>bridge.connectRemote(url));
});
bridge.onProgress(message=>report(String(message)));
bridge.status().then(config=>{
  if (!config.ok) return report(config.error||'桌面配置加载失败',true);
  if (config.url && config.url.startsWith('https://')) byId('server-url').value=config.url;
  show(config.mode);
}).catch(error=>report(error.message,true));
