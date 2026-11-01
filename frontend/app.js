/* WeiGuang Math minimal studio, real FastAPI operations, no decorative widgets. */
(() => {
  'use strict';
  const root = document.getElementById('app');
  const $ = sel => document.querySelector(sel);
  const state = {
    route:'work', lessons:[], videos:[], projects:[], selected:new Set(), projectSelected:new Set(), search:'',
    lesson:null, script:'', teacher:null, curriculum:null, pendingEdit:null, job:null, loading:false, error:'',
    modal:null, notice:'', trash:[], projectTrash:[], settings:null,
    ai:{catalog:[],providers:[],bindings:{},status:null,providerId:'',preset:'openai',
        versions:[],discovery:'',modelId:'',targetTask:'all',testStatus:''},
  };
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, s => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
  }[s]));
  const api = async (path, options={}) => {
    const headers={...(options.headers || {})};
    if (options.body && !(options.body instanceof FormData)) {
      headers['Content-Type']='application/json';
      options.body=JSON.stringify(options.body);
    }
    const response=await fetch('/api/v1'+path,{...options,headers});
    if (!response.ok) {
      if (response.status===401 && path!=='/auth/login') {
        state.route='login';
        render();
      }
      let message='';
      try {const body=await response.json();message=body.detail || JSON.stringify(body);}
      catch {message='请求失败';}
      throw new Error(message+' ('+response.status+')');
    }
    if (options.responseType==='blob') return response.blob();
    return response.json();
  };
  const options = (method,body) => ({method,body});
  const flash = (message,error=false) => {
    const old=$('.toast');if(old)old.remove();
    const toast=document.createElement('div');
    toast.className='toast';toast.textContent=message;
    if(error)toast.style.background='#7b3434';
    document.body.appendChild(toast);
    setTimeout(()=>toast.remove(),4200);
  };
  const exec = async fn => {
    try {state.loading=true;await fn();}
    catch (error) {flash(error.message||'操作失败',true);}
    finally {state.loading=false;render();}
  };
  const label = s => ({
    draft:'草稿',package_needed:'待准备',teacher_review_pending:'待审核教学草稿',curriculum_review_pending:'待审核课堂编排',script_pending:'待审核',
    approved:'已审核',ready:'已完成',queued:'排队中',
    running:'制作中',failed:'失败',preview_ready:'可预览',
  }[s]||s||'未开始');
  const pill = status => '<span class="status"><i class="dot '+(
    status==='ready'?'ready':status==='running'?'running':status==='failed'?'failed':''
  )+'"></i>'+escapeHTML(label(status))+'</span>';
  const allRows=()=>state.lessons.filter(l => l.title.toLowerCase().includes(state.search.toLowerCase()));
  const button=(text,action,klass='')=>'<button class="btn '+klass+'" data-action="'+action+'">'+text+'</button>';
  const icons={
    plus:'＋',edit:'✎',download:'↓',view:'↗',trash:'×',back:'←',
  };
  const nav = () => '<header class="topbar">'+
    '<a class="brand" href="#" data-route="work" aria-label="微光数学工作台"><img src="./logo.svg" alt="微光数学"/></a>'+
    '<nav class="topnav" aria-label="主导航">'+
    [['work','工作台'],['library','视频库'],['settings','设置']].map(([route,title])=>
    '<button class="navlink '+(state.route===route?'active':'')+
    '" data-route="'+route+'">'+title+'</button>').join('')+
    '</nav></header>';
  const head=(title,more='')=>'<div class="page-head"><h1>'+title+'</h1><div class="actions">'+more+'</div></div>';
  const blank = (caption) => '<div class="blank"><svg width="47" height="47" viewBox="0 0 47 47" fill="none" aria-hidden="true"><rect x="6" y="8" width="35" height="29" rx="6" stroke="#999" stroke-width="1.5"/><path d="m20 17 12 6-12 7z" stroke="#999" stroke-width="1.5"/></svg><span>'+caption+'</span></div>';

  const work = () => head('制作视频')+
    '<div class="work-grid"><section>'+
    '<form id="create-form">'+
    '<div class="field"><label for="title">视频名称</label><input class="input" id="title" name="title" required maxlength="180" placeholder="例如：定积分与换元法"></div>'+
    '<div class="field"><label for="problem">数学题目</label><textarea class="area" id="problem" name="problem" required placeholder="输入题目、条件及设问"></textarea></div>'+
    '<div class="field"><label for="solution">参考解析</label><textarea class="area" id="solution" name="reference_solution" required placeholder="输入完整参考解析"></textarea></div>'+
    '<div class="field"><label for="project">所属项目</label><select class="select" id="project" name="project_id"><option value="">未分组</option>'+
    state.projects.map(p=>'<option value="'+escapeHTML(p.id)+'">'+escapeHTML(p.title)+'</option>').join('')+
    '</select></div>'+
    '<div class="cols"><div class="field"><label for="voice">音色</label><select class="select" id="voice" name="voice">'+
    '<option value="zh-CN-YunxiNeural">云希</option><option value="zh-CN-XiaoxiaoNeural">晓晓</option></select></div>'+
    '<div class="field"><label for="fps">帧率</label><select class="select" id="fps" name="fps">'+
    '<option value="60">60 FPS</option><option value="30">30 FPS</option></select></div></div>'+
    '<button type="submit" class="btn primary" style="width:100%">创建课程</button>'+
    '</form></section><aside class="panel airy">'+
    '<div class="row spread"><h2>当前进度</h2>'+pill(state.job?.status || 'draft')+'</div>'+
    (state.job ? '<div class="notice">'+escapeHTML(state.job.phase || label(state.job.status))+'</div>'+
     '<div class="row">'+button('查看任务','show-job')+'</div>':blank('创建课程后在这里查看制作进度'))+
    '</aside></div>';

  const row = l => '<tr><td><input class="check select-item" type="checkbox" value="'+escapeHTML(l.id)+
    '" '+(state.selected.has(l.id)?'checked':'')+' aria-label="选择 '+escapeHTML(l.title)+'"/></td>'+
    '<td><span class="title-cell" data-open="'+escapeHTML(l.id)+'">'+escapeHTML(l.title)+'</span></td>'+
    '<td>'+pill(l.status)+'</td>'+
    '<td class="muted small hide-small">'+escapeHTML((l.updated_at||'').slice(0,10))+'</td>'+
    '<td><div class="links">'+
    '<button class="iconbtn" data-open="'+escapeHTML(l.id)+'" title="查看">查看</button>'+
    (l.has_video?'<a class="iconbtn" href="/api/v1/videos/'+escapeHTML(l.id)+'/download" title="下载">下载</a>':'')+
    '<button class="iconbtn" data-rename="'+escapeHTML(l.id)+'" title="重命名">编辑</button>'+
    '<button class="iconbtn" data-delete="'+escapeHTML(l.id)+'" title="删除">删除</button>'+
    '</div></td></tr>';

  const library = () => head('视频库',button('导出全部记录','export')+button('＋ 新建','new','primary'))+
    '<div class="toolbar"><input class="input" id="search" placeholder="搜索视频..." value="'+escapeHTML(state.search)+'"/>'+
    '<div class="actions">'+button('回收站','trash')+button('批量删除','batch-delete','danger')+'</div></div>'+
    '<div class="table-wrap"><table><thead><tr><th><input class="check" id="select-all" type="checkbox" '+
    (allRows().length>0 && allRows().every(l=>state.selected.has(l.id))?'checked':'')+
    ' aria-label="全选"/></th><th>名称</th><th>状态</th><th class="hide-small">更新日期</th><th>操作</th></tr></thead><tbody>'+
    (allRows().length?allRows().map(row).join(''):'<tr><td colspan="5"><div class="empty-row">暂无视频</div></td></tr>')+
    '</tbody></table></div>'+
    (state.selected.size?'<div class="bar"><span>已选 '+state.selected.size+' 项</span><div class="actions">'+
    button('取消选择','clear-selection')+button('删除所选','batch-delete','danger')+'</div></div>':'');
  
  const detail = () => {
    const l=state.lesson;
    if(!l)return head('视频详情')+blank('正在读取课程');
    const video=l.has_video ?
      '<video controls preload="metadata" src="/api/v1/videos/'+escapeHTML(l.id)+'/stream"></video>' :
      '<div class="video-placeholder"><div style="font-size:32px;margin-bottom:10px">▷</div>'+escapeHTML(label(l.status))+'</div>';
    const actions=l.has_video ?
      '<a class="btn" href="/api/v1/videos/'+escapeHTML(l.id)+'/download">↓ 下载 MP4</a>'+
      button('修改名称','rename-current') :
      (l.status==='approved'?button('开始渲染','start-render','primary'):'');
    return head('<span style="font-size:13px;cursor:pointer;color:#777" data-route="library">← 视频库</span>')+
      '<div class="video-card"><div class="row spread" style="margin-bottom:18px"><h1>'+escapeHTML(l.title)+'</h1>'+pill(l.status)+'</div>'+
      '<div class="video-wrap">'+video+'</div><div class="row spread" style="margin-top:16px">'+
      '<span class="muted small">1280 × 720 · '+escapeHTML(l.fps)+' FPS</span>'+
      '<div class="actions">'+actions+'</div></div>'+
      (state.job&&state.job.lesson_id===l.id?
      '<div class="notice">任务：'+escapeHTML(state.job.phase||label(state.job.status))+
      (state.job.status==='failed'?'<div style="margin-top:12px">'+
      button('重试任务','retry-job')+'</div>':'')+'</div>':'')+
      ((l.status==='draft'||l.status==='package_needed'||l.status==='teacher_review_pending'||l.status==='curriculum_review_pending')?
        '<div class="edit-section"><h2>课程资料</h2><div class="actions" style="margin-bottom:19px">'+
        (l.status==='draft'?button('生成教学草稿','generate-teacher','primary'):'')+
        (l.status==='package_needed'?button('编排完整课堂','generate-curriculum','primary'):'')+
        (l.status==='teacher_review_pending'?button('查看教学草稿','view-teacher','primary'):'')+
        (l.status==='curriculum_review_pending'?button('审核课堂编排','view-curriculum','primary'):'')+
        '</div><div class="upload"><input type="file" id="package-upload" accept=".zip"/>'+
        button('上传已审核课程包','upload-package')+'</div></div>':'')+
      (l.status==='script_pending'?'<div class="edit-section"><h2>讲稿审核</h2>'+button('查看完整讲稿','open-review','primary')+'</div>':'')+
      (state.pendingEdit?'<div class="notice"><div class="row spread"><span>微调候选：'+escapeHTML(label(state.pendingEdit.status))+'</span>'+
        button('审核修改','view-edit-review')+'</div></div>':'')+
      (l.has_video?'<section class="edit-section"><h2>继续微调</h2>'+
        '<textarea class="area" id="instruction" placeholder="输入要修改的地方，可一次提出多个要求"></textarea>'+
        '<div class="row spread" style="margin-top:14px"><span class="muted small">只显示最新成功视频</span>'+
        button('提交微调','send-edit','primary')+'</div>'+
        '<div class="row" style="margin-top:18px">'+button('满意，结束微调','satisfied')+'</div></section>':'')+
      '</div>';
  };
  const teacherView = () => head('教学草稿',button('返回课程','back-to-detail'))+
    '<div class="video-card"><h2>教学安排</h2>'+
    '<div class="script">'+(state.teacher?.plan?.teaching_events||[]).map(
      (entry,i)=>'<div style="padding:10px 0"><strong>'+
      (i+1)+'. '+escapeHTML(entry.event_type)+'</strong><div>'+
      escapeHTML(entry.teaching_goal)+'</div></div>'
    ).join('')+'</div>'+
    '<div class="field" style="margin-top:24px"><label for="teacher-reviewer">审核人</label>'+
    '<input class="input" id="teacher-reviewer" placeholder="填写实际审核人标识"></div>'+
    '<label class="row" style="margin-bottom:22px"><input class="check" type="checkbox" id="teacher-check">已核对数学推导与教学步骤</label>'+
    button('确认教学草稿','approve-teacher','primary')+'</div>';
  const curriculumView = () => head('课堂编排审核',button('返回课程','back-to-detail'))+
    '<div class="video-card"><h2>教学事件与板书</h2>'+
    '<div class="script">'+(state.curriculum?.units||[]).map((u,i)=>
      '<div style="padding:13px 0;border-bottom:1px solid #f1f1f1"><strong>'+
      (i+1)+'. '+escapeHTML(u.heading)+'</strong><div>'+
      escapeHTML(u.detail)+'</div><div class="muted small">'+
      (u.math||[]).map(x=>escapeHTML(x.latex)).join(' · ')+'</div></div>'
    ).join('')+'</div>'+
    '<div class="field" style="margin-top:24px"><label for="curriculum-reviewer">审核人</label>'+
    '<input class="input" id="curriculum-reviewer" placeholder="填写审核人"></div>'+
    '<label class="row" style="margin-bottom:22px"><input class="check" type="checkbox" id="curriculum-check">已核对数学、板书与口播</label>'+
    button('确认课堂编排','approve-curriculum','primary')+'</div>';
  const editReview = () => {
    const p=state.pendingEdit;
    if(!p)return head('微调审核')+blank('没有待审核的微调');
    return head('微调审核',button('返回视频','back-to-detail'))+
      '<div class="video-card"><h2>本轮要求</h2><div class="script">'+
      escapeHTML(p.original_instruction)+'</div>'+
      '<h2 style="margin-top:30px">修改计划</h2><div class="script">'+
      (p.requirements||[]).map((x,i)=>(i+1)+'. '+escapeHTML(x.instruction)+
      ' · '+escapeHTML(x.target)).join('<hr class="hr"/>')+'</div>'+
      (p.script?'<h2 style="margin-top:30px">完整口播与板书脚本</h2>'+
      '<div class="script">'+escapeHTML(p.script)+'</div>':'')+
      '<div class="field" style="margin-top:24px"><label for="edit-reviewer">审核人</label>'+
      '<input class="input" id="edit-reviewer" placeholder="填写审核人"></div>'+
      '<label class="row" style="margin-bottom:20px"><input class="check" type="checkbox" id="edit-review-check">已检查本轮数学与讲稿</label>'+
      '<div class="actions">'+button('批准并生成视频','approve-edit','primary')+
      button('退回修改','reject-edit')+'</div></div>';
  };
  const review = () => head('讲稿审核',button('返回课程','back-to-detail'))+
    '<div class="video-card"><div class="row spread" style="margin-bottom:17px"><h2>完整教师讲稿</h2><span class="muted small">待审核</span></div>'+
    '<div class="script" id="script-content">'+escapeHTML(state.script)+'</div>'+
    '<div class="field" style="margin-top:24px"><label for="reviewer">审核人</label>'+
    '<input class="input" id="reviewer" placeholder="填写实际审核人标识"></div>'+
    '<label class="row" style="margin-bottom:22px"><input type="checkbox" class="check" id="review-check">确认已经检查讲稿及数学内容</label>'+
    '<div class="actions">'+button('确认通过','approve','primary')+button('返回','back-to-detail')+'</div></div>';
  const login = () => '<div class="video-card" style="max-width:420px;margin:95px auto">'+
    '<h1 style="margin-bottom:32px">登录微光数学</h1>'+
    '<form id="login-form"><div class="field"><label for="login-secret">访问密钥</label>'+
    '<input class="input" id="login-secret" type="password" autocomplete="current-password" required></div>'+
    '<button type="submit" class="btn primary" style="width:100%">登录</button></form></div>';
  const settings = () => head('设置')+'<div class="settings-list">'+
    '<h2>视频</h2><div class="setting-row"><span>默认音色</span><select class="select" id="setting-voice">'+
    '<option value="zh-CN-YunxiNeural">云希</option><option value="zh-CN-XiaoxiaoNeural">晓晓</option></select></div>'+
    '<div class="setting-row"><span>默认帧率</span><select class="select" id="setting-fps"><option value="60">60 FPS</option><option value="30">30 FPS</option></select></div>'+
    '<div class="setting-row"><span>视频分辨率</span><span class="muted">1280 × 720</span></div>'+
    '<h2 style="margin-top:40px">系统</h2>'+
    '<div class="setting-row"><span>数学教师模型</span><span class="muted">'+(state.settings?.teacher_ai_configured?'已配置':'需要后端配置')+'</span></div>'+
    '<div class="setting-row"><span>微调模型</span><span class="muted">'+(state.settings?.ai_configured?'已配置':'需要后端配置')+'</span></div>'+
    '<div class="setting-row"><span>统一 API / 模型版本</span>'+button('管理模型 API','open-ai-settings')+'</div>'+
    '<div class="setting-row"><span>任务并发</span><span class="muted">1 个渲染任务</span></div>'+
    '<div style="margin-top:26px">'+button('保存偏好','save-settings','primary')+'</div>'+
    '<hr class="hr"/><div class="row spread"><h2 style="margin-bottom:0">项目</h2><div class="actions">'+
    button('新建','new-project')+button('批量删除','delete-projects','danger')+
    button('回收站','project-trash')+'</div></div>'+
    '<div class="table-wrap" style="margin-top:16px"><table><thead><tr><th>选择</th><th>项目</th><th>操作</th></tr></thead><tbody>'+
    (state.projects.length?state.projects.map(p=>
      '<tr><td><input class="check project-item" type="checkbox" value="'+escapeHTML(p.id)+'" '+(state.projectSelected.has(p.id)?'checked':'')+'/></td><td>'+escapeHTML(p.title)+'</td>'+
      '<td><button class="iconbtn" data-rename-project="'+escapeHTML(p.id)+'">编辑</button>'+
      '<button class="iconbtn" data-delete-project="'+escapeHTML(p.id)+'">删除</button></td></tr>'
    ).join(''):'<tr><td colspan="3">暂无项目</td></tr>')+
    '</tbody></table></div></div>';
  const trash = () => head('回收站',button('返回视频库','go-library'))+
    '<div class="table-wrap"><table><thead><tr><th>序号</th><th>视频名称</th><th>操作</th></tr></thead><tbody>'+
    (state.trash.length?state.trash.map((l,i)=>
    '<tr><td>'+String(i+1)+'</td><td>'+escapeHTML(l.title)+'</td>'+
    '<td>'+button('恢复','restore-'+escapeHTML(l.id))+'</td></tr>').join('') :
    '<tr><td colspan="3"><div class="empty-row">回收站为空</div></td></tr>')+
    '</tbody></table></div>';
  const modal = () => !state.modal ? '' : '<div class="modal-backdrop"><div class="modal">'+
    '<h2>'+escapeHTML(state.modal.title)+'</h2><p>'+escapeHTML(state.modal.message)+'</p>'+
    '<div class="actions" style="justify-content:flex-end">'+button('取消','close-modal')+
    button('确认删除','confirm-delete','danger')+'</div></div></div>';
  const render = () => {
    root.innerHTML=nav()+'<main class="main">'+(
      state.route==='work'?work():state.route==='library'?library():
      state.route==='detail'?detail():state.route==='review'?review():
      state.route==='teacher'?teacherView():state.route==='curriculum'?curriculumView():
      state.route==='edit-review'?editReview():state.route==='ai'?modelSettings():
      state.route==='trash'?trash():state.route==='login'?login():settings()
    )+'</main>'+modal();
    if(state.route==='work') {
      const prefs=JSON.parse(localStorage.getItem('wg-prefs')||'{}');
      if(prefs.voice)$('#voice').value=prefs.voice;
      if(prefs.fps)$('#fps').value=String(prefs.fps);
    }
    if(state.route==='settings') {
      const prefs=JSON.parse(localStorage.getItem('wg-prefs')||'{}');
      if(prefs.voice)$('#setting-voice').value=prefs.voice;
      if(prefs.fps)$('#setting-fps').value=String(prefs.fps);
    }
  };
  const refreshAI = async (selectedId) => {
    const [catalog,providers,bindings,status]=await Promise.all([
      api('/ai/catalog'),api('/ai/providers'),api('/ai/selections'),api('/ai/status'),
    ]);
    state.ai.catalog=catalog.providers;
    state.ai.providers=providers;
    state.ai.bindings=bindings;
    state.ai.status=status;
    state.ai.providerId=selectedId!==undefined?selectedId:
      (providers.some(p=>p.id===state.ai.providerId)?state.ai.providerId:
       (providers[0]?.id||''));
    state.ai.versions=[];
    state.ai.discovery='';
    state.ai.testStatus='';
  };
  const refresh = async () => {
    [state.lessons,state.videos,state.projects]=await Promise.all([
      api('/lessons'),api('/videos'),api('/projects'),
    ]);
  };
  const selectLesson = async id => {
    const [lesson,jobs,pending]=await Promise.all([
      api('/lessons/'+encodeURIComponent(id)),
      api('/jobs?lesson_id='+encodeURIComponent(id)+'&limit=1'),
      api('/videos/'+encodeURIComponent(id)+'/edits/pending'),
    ]);
    state.lesson=lesson;
    state.job=jobs[0]||null;
    state.pendingEdit=pending.pending;
    state.route='detail';render();
    if(state.job && ['queued','running'].includes(state.job.status)){
      watch(state.job.id);
    }
  };
  const watch = id => {
    let rounds=0;
    const tick=async () => {
      try {
        state.job=await api('/jobs/'+encodeURIComponent(id));
        if(state.job.status==='succeeded' || state.job.status==='failed' ||
           state.job.status==='cancelled'){
          await refresh();
          if(state.lesson)await selectLesson(state.lesson.id);
          render();
          flash(state.job.status==='succeeded'?'任务完成':state.job.error||'任务失败',
                state.job.status!=='succeeded');
          return;
        }
        render();
        if(++rounds<600)setTimeout(tick,1500);
      } catch(e){flash(e.message,true);}
    };
    setTimeout(tick,600);
  };

  document.addEventListener('submit', event => {
    if(event.target.id==='login-form'){
      event.preventDefault();
      const token=$('#login-secret').value;
      exec(async()=>{
        await api('/auth/login',options('POST',{token}));
        state.route='work';
        await refresh();
        state.settings=await api('/settings');
        flash('已登录');
      });
      return;
    }
    if(event.target.id!=='create-form')return;
    event.preventDefault();
    const form=new FormData(event.target);
    exec(async()=>{
      const l=await api('/lessons',options('POST',{
        title:form.get('title'),problem:form.get('problem'),
        reference_solution:form.get('reference_solution'),
        project_id:form.get('project_id')||null,
        voice:form.get('voice'),fps:Number(form.get('fps')),
      }));
      await refresh();
      await selectLesson(l.id);
      flash('课程已创建');
    });
  });
  document.addEventListener('input',event=>{
    if(event.target.id==='search'){
      state.search=event.target.value;
      const rows=$('tbody');
      if(rows){rows.innerHTML=allRows().length?allRows().map(row).join(''):
      '<tr><td colspan="5"><div class="empty-row">无匹配结果</div></td></tr>';}
    }
  });
  document.addEventListener('change',event=>{
    if(event.target.id==='select-all'){
      for(const l of allRows()){
        if(event.target.checked)state.selected.add(l.id);else state.selected.delete(l.id);
      }
      render();
    }
    if(event.target.classList.contains('select-item')){
      if(event.target.checked)state.selected.add(event.target.value);
      else state.selected.delete(event.target.value);
      render();
    }
    if(event.target.classList.contains('project-item')){
      if(event.target.checked)state.projectSelected.add(event.target.value);
      else state.projectSelected.delete(event.target.value);
      render();
    }
    if(event.target.id==='ai-provider-choice'){
      state.ai.providerId=event.target.value;
      state.ai.versions=[];
      state.ai.modelId='';
      state.ai.testStatus='';
      render();
    }
    if(event.target.id==='ai-preset'){
      const item=state.ai.catalog.find(p=>p.id===event.target.value);
      if(item){
        state.ai.preset=item.id;
        $('#ai-name').value=item.label;
        $('#ai-url').value=item.base_url;
        $('#ai-protocol').value=item.protocol;
      }
    }
    if(event.target.id==='ai-versions' && event.target.value){
      state.ai.modelId=event.target.value;
      $('#ai-manual-model').value=event.target.value;
    }
    if(event.target.id==='ai-target'){
      state.ai.targetTask=event.target.value;
    }
  });
  document.addEventListener('click',event=>{
    const route=event.target.closest('[data-route]');
    if(route){event.preventDefault();state.route=route.dataset.route;
      if(state.route==='library')exec(refresh);else render();return;}
    const open=event.target.closest('[data-open]');
    if(open){exec(()=>selectLesson(open.dataset.open));return;}
    const rename=event.target.closest('[data-rename]');
    if(rename){
      exec(async()=>{
        const l=state.lessons.find(x=>x.id===rename.dataset.rename);
        const name=window.prompt('视频名称',l.title);
        if(!name||!name.trim())return;
        await api('/videos/'+l.id,options('PATCH',{title:name.trim()}));
        await refresh();flash('已修改名称');
      });return;
    }
    const remove=event.target.closest('[data-delete]');
    if(remove){state.modal={title:'删除视频',message:'确认将此视频移入回收站？',
      ids:[remove.dataset.delete]};render();return;}
    const projectRename=event.target.closest('[data-rename-project]');
    if(projectRename){
      const p=state.projects.find(x=>x.id===projectRename.dataset.renameProject);
      if(!p)return;
      const title=window.prompt('项目名称',p.title);
      if(!title||!title.trim())return;
      exec(async()=>{await api('/projects/'+p.id,options('PATCH',{title:title.trim()}));await refresh();flash('已修改');});
      return;
    }
    const projectDelete=event.target.closest('[data-delete-project]');
    if(projectDelete){
      state.modal={title:'删除项目',message:'所含视频也将移入回收站。确认删除？',
        kind:'projects',ids:[projectDelete.dataset.deleteProject]};
      render();return;
    }
    const action=event.target.closest('[data-action]');
    if(!action)return;
    const id=action.dataset.action;
    if(id==='new'){state.route='work';render();}
    else if(id==='trash'){exec(async()=>{state.trash=await api('/trash');state.route='trash';});}
    else if(id==='new-project'){
      const title=window.prompt('项目名称','');
      if(!title||!title.trim())return;
      exec(async()=>{await api('/projects',options('POST',{title:title.trim()}));await refresh();flash('已创建项目');});
    }
    else if(id==='delete-projects'){
      if(!state.projectSelected.size)return flash('请选择项目');
      state.modal={title:'批量删除项目',message:'确认删除 '+state.projectSelected.size+' 个项目及其关联视频？',
        kind:'projects',ids:[...state.projectSelected]};
      render();
    }
    else if(id==='project-trash'){
      exec(async()=>{
        state.projectTrash=await api('/projects/trash');
        if(!state.projectTrash.length)return flash('没有已删除的项目');
        const titles=state.projectTrash.map(x=>x.title).join('、');
        if(!window.confirm('恢复已删除项目及其关联视频？'+titles))return;
        await api('/projects/restore',options('POST',{ids:state.projectTrash.map(x=>x.id)}));
        await refresh();flash('已恢复项目');
      });
    }
    else if(id==='go-library'){state.route='library';exec(refresh);}
    else if(id==='clear-selection'){state.selected.clear();render();}
    else if(id==='batch-delete'){
      if(!state.selected.size)return flash('请先选择视频');
      state.modal={title:'批量删除',message:'确认删除已选择的 '+state.selected.size+' 个视频？',
      ids:[...state.selected]};render();
    } else if(id==='close-modal'){state.modal=null;render();}
    else if(id==='confirm-delete'){
      exec(async()=>{
        const ids=state.modal.ids;
        const projects=state.modal.kind==='projects';
        await api(projects?'/projects/batch-delete':'/videos/batch-delete',
          options('POST',{ids}));
        state.modal=null;state.selected.clear();state.projectSelected.clear();
        await refresh();flash('已移入回收站');
      });
    } else if(id==='export'){
      exec(async()=>{
        const blob=await api('/system/edit-history/export',{responseType:'blob'});
        const url=URL.createObjectURL(blob);
        const a=document.createElement('a');a.href=url;a.download='weiguang_all_edit_history.json';
        a.click();URL.revokeObjectURL(url);
        flash('已导出全部微调记录');
      });
    } else if(id==='upload-package'){
      const file=$('#package-upload')?.files?.[0];
      if(!file)return flash('请选择课程包 ZIP');
      exec(async()=>{
        const data=new FormData();data.append('file',file);
        await api('/lessons/'+state.lesson.id+'/package',{method:'POST',body:data});
        await selectLesson(state.lesson.id);await refresh();flash('课程包验证通过');
      });
    } else if(id==='generate-teacher'){
      exec(async()=>{
        const task=await api('/lessons/'+state.lesson.id+'/prepare',
          options('POST',{}));
        state.job=task;
        watch(task.id);
        flash('教学草稿生成任务已提交');
      });
    } else if(id==='generate-curriculum'){
      exec(async()=>{
        const task=await api('/lessons/'+state.lesson.id+'/curriculum/prepare',
          options('POST',{}));
        state.job=task;watch(task.id);
        flash('课堂编排任务已创建');
      });
    } else if(id==='view-curriculum'){
      exec(async()=>{
        state.curriculum=await api('/lessons/'+state.lesson.id+'/curriculum');
        state.route='curriculum';
      });
    } else if(id==='approve-curriculum'){
      const reviewer=$('#curriculum-reviewer')?.value?.trim();
      if(!reviewer||!$('#curriculum-check')?.checked)
        return flash('请先检查数学、板书与口播',true);
      exec(async()=>{
        await api('/lessons/'+state.lesson.id+'/curriculum/approve',
          options('POST',{reviewer,confirmed:true}));
        await selectLesson(state.lesson.id);
        await refresh();flash('课堂编排已审核，可继续检查完整讲稿');
      });
    } else if(id==='view-teacher'){
      exec(async()=>{
        state.teacher=await api('/lessons/'+state.lesson.id+'/teaching');
        state.route='teacher';
      });
    } else if(id==='approve-teacher'){
      const reviewer=$('#teacher-reviewer')?.value?.trim();
      if(!reviewer||!$('#teacher-check')?.checked)return flash('请先检查数学内容',true);
      exec(async()=>{
        await api('/lessons/'+state.lesson.id+'/teaching/review',
          options('POST',{reviewer,confirmed:true}));
        await selectLesson(state.lesson.id);
        await refresh();
        flash('教学草稿已确认；下一步需要经过审核的课程数据');
      });
    } else if(id==='open-review'){
      exec(async()=>{
        const payload=await api('/lessons/'+state.lesson.id+'/script');
        state.script=payload.script;state.route='review';flash('讲稿已准备');
      });
    } else if(id==='back-to-detail'){
      state.route='detail';render();
    } else if(id==='approve'){
      const reviewer=$('#reviewer')?.value?.trim();
      const confirmed=$('#review-check')?.checked;
      if(!reviewer||!confirmed)return flash('请填写审核人并确认已核对',true);
      exec(async()=>{
        await api('/lessons/'+state.lesson.id+'/approve',
          options('POST',{reviewer,confirmed:true}));
        await selectLesson(state.lesson.id);
        await refresh();flash('讲稿审核通过');
      });
    } else if(id==='retry-job'){
      if(!state.job)return;
      exec(async()=>{
        const retry=await api('/jobs/'+state.job.id+'/retry',options('POST',{}));
        state.job=retry;watch(retry.id);flash('已重新排队');
      });
    } else if(id==='start-render'){
      exec(async()=>{
        const result=await api('/lessons/'+state.lesson.id+'/render',options('POST',{}));
        state.job=result;
        watch(result.id);flash('渲染任务已创建');
      });
    } else if(id==='view-edit-review'){
      state.route='edit-review';render();
    } else if(id==='approve-edit'){
      const reviewer=$('#edit-reviewer')?.value?.trim();
      if(!reviewer||!$('#edit-review-check')?.checked)
        return flash('请核对修改内容并填写审核人',true);
      exec(async()=>{
        const record=state.pendingEdit;
        const response=await api(
          '/videos/'+state.lesson.id+'/edits/'+record.edit_id+'/approve',
          options('POST',{reviewer,confirmed:true}),
        );
        state.job=response.job;
        await selectLesson(state.lesson.id);
        watch(response.job.id);
        flash('审核已通过，开始生成新版视频');
      });
    } else if(id==='reject-edit'){
      exec(async()=>{
        const record=state.pendingEdit;
        await api('/videos/'+state.lesson.id+'/edits/'+record.edit_id+'/reject',
          options('POST',{}));
        state.pendingEdit=null;
        await selectLesson(state.lesson.id);
        flash('已退回此轮修改');
      });
    } else if(id==='send-edit'){
      const instruction=$('#instruction')?.value?.trim();
      if(!instruction)return flash('请输入微调要求',true);
      exec(async()=>{
        const result=await api('/videos/'+state.lesson.id+'/edits',
          options('POST',{instruction}));
        state.job=result.job;watch(result.job.id);flash('微调任务已提交');
      });
    } else if(id==='satisfied'){
      exec(async()=>{
        await api('/videos/'+state.lesson.id+'/feedback',
          options('POST',{feedback:'已确认满意',satisfied:true}));
        flash('已确认满意');
      });
    } else if(id==='rename-current'){
      const l=state.lesson;
      const name=window.prompt('视频名称',l.title);
      if(!name||!name.trim())return;
      exec(async()=>{
        await api('/videos/'+l.id,options('PATCH',{title:name.trim()}));
        await selectLesson(l.id);await refresh();
      });
    } else if(id==='save-settings'){
      const prefs={voice:$('#setting-voice').value,fps:Number($('#setting-fps').value)};
      localStorage.setItem('wg-prefs',JSON.stringify(prefs));
      flash('已保存默认偏好');
    } else if(id==='show-job'){
      state.route='detail';
      if(state.job?.lesson_id)exec(()=>selectLesson(state.job.lesson_id));
      else render();
    } else if(id.startsWith('restore-')){
      exec(async()=>{
        await api('/trash/restore',options('POST',{ids:[id.slice(8)]}));
        state.trash=await api('/trash');await refresh();flash('已恢复');
      });
    }
  });
  // Actual API data only; never substitute fake successful movies.
  render();
  exec(async()=>{await refresh();state.settings=await api('/settings');});
})();
