import { App } from '@modelcontextprotocol/ext-apps';
import { transferPhoto } from './upload-diagnostics.mjs';
const app = new App({ name: 'KINU TABI AI Try-on', version: '0.1.0' }, {});
const $ = id => document.getElementById(id);
const node = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
const active = job => ['QUEUED','VALIDATING','GENERATING'].includes(job.status);
const labels = { QUEUED:'等待 worker 處理',VALIDATING:'正在檢查來源',GENERATING:'正在生成',SUCCEEDED:'生成完成',FAILED:'生成失敗',EXPIRED:'圖片已到期',DELETED:'圖片已刪除' };
let data, source, review, connected = false, busy = false, media = {}, pollTimer, expiryTimer, websiteOpen;
let photoConsent, selectedFile, pendingUpload;
const jobs = new Map();
function status(message, error=false) { $('status').textContent = message; $('status').dataset.error = String(error); }
function controls() {
  document.querySelectorAll('button').forEach(b => { b.disabled = busy || !connected || !data; });
  $('prepare').disabled = busy || !connected || !source;
  $('photo-file').disabled = busy || !photoConsent;
  $('photo-consent').disabled = busy || !photoConsent;
  $('submit-photo').disabled = busy || !connected || !selectedFile || !$('photo-consent').checked;
  $('submit-photo').textContent = pendingUpload ? (pendingUpload.transferred ? '重試照片檢查' : '重試本次上傳') : '同意並上傳照片';
}
function picture(id, alt, expiresAt, existing) {
  const raw = media[id]; if (!raw) return node('p','圖片尚未提供或需重新查詢','muted');
  let url; try { url = new URL(raw); } catch { return node('p','圖片網址無效','muted'); }
  if (!['http:','https:'].includes(url.protocol)) return node('p','圖片網址無效','muted');
  const remaining = expiresAt ? new Date(expiresAt).getTime() - Date.now() : Infinity;
  if (remaining <= 0) return node('p','圖片已到期','muted');
  if (existing?.src === url.href && existing.complete && existing.naturalWidth > 0) return existing;
  const img = node('img'); img.src = url.href; img.alt = alt; img.referrerPolicy = 'no-referrer'; img.dataset.mediaId = id;
  img.addEventListener('error', () => img.replaceWith(node('p', expiresAt ? '圖片載入失敗或網址已到期，請按「更新本次圖片」。更新不會生成或扣額度。' : '人物圖片載入失敗，請按「刷新照片與額度」。','muted')), { once:true });
  if (Number.isFinite(remaining)) setTimeout(() => { if (img.isConnected) { media[id]=null; renderJobs(); } }, remaining);
  return img;
}
function unpack(result) {
  if (result.isError) { const error=new Error(result.content?.find(c => c.type === 'text')?.text || '試穿操作失敗。'); error.code=result.structuredContent?.error?.code; throw error; }
  if (!result.structuredContent) throw new Error('無法辨識試穿回應。');
  Object.assign(media, result._meta?.media || {});
  return result.structuredContent;
}
async function call(name, args, options) { return unpack(await app.callServerTool({ name, arguments: args }, options)); }
async function sync() {
  try { await app.updateModelContext({ content: [{ type:'text',text: 'KINU TABI 試穿進度：' + JSON.stringify({
    conversationId:data?.conversationId, planId:data?.planId, kimonoId:data?.kimonoId,
    source, reviewId:review?.reviewId, jobs:[...jobs.values()].map(j => ({ jobId:j.jobId,status:j.status,kimonoId:j.kimonoId,expiresAt:j.expiresAt })), websiteOpen,
    notice:'選人物與進度同步不代表生成確認；重新生成需再次明確確認。尚未建立預約。',
  }) }] }); } catch { status('畫面已更新，AI 上下文未確認同步；任務仍可用任務編號恢復。',true); }
}
async function run(action) {
  if (busy) return;
  busy = true; controls();
  try { await action(); } catch (e) { status(e.message || '操作失敗，請重試。',true); }
  finally { busy = false; controls(); }
}
function showReview() {
  const root = $('review'); root.replaceChildren(); root.hidden = !review;
  clearTimeout(expiryTimer);
  if (!review) return;
  root.append(node('h2','確認本次 AI 試穿'), node('p',`${review.planName}／${review.kimonoName}`),
    node('p',review.source === 'MODEL' ? `人物：${review.modelName}` : `人物：本人照片 ${review.photoId}`),
    node('p',`今日 MCP 剩餘 ${review.usage.mcp.remaining} 次；每日最多 3 次。`),
    node('p',review.notice,'muted'), node('p',`此確認有效至 ${new Date(review.reviewExpiresAt).toLocaleString('zh-TW')}`,'muted'));
  if (review.isDemo) root.append(node('p','示範商品；試穿仍會呼叫真實 AI 服務並使用額度。','muted'));
  const consentLabel = node('label'); const consent = node('input'); consent.type='checkbox';
  consentLabel.append(consent,document.createTextNode(' 我確認以上人物、款式與額度／到期規則，並同意本次生成。')); root.append(consentLabel);
  const confirm = node('button','確認並生成','primary');
  confirm.addEventListener('click', () => run(async () => {
    if (!consent.checked) throw new Error('請先勾選本次生成確認。');
    const r = await call('confirm_try_on',{reviewId:review.reviewId,confirmed:true});
    jobs.set(r.jobId,r); review=null; showReview(); if (r.usage) { data.usage=r.usage; renderSources(); } renderJobs(); await sync(); schedulePoll();
    status('已取得任務；重複送出同一確認不會重複扣額度。可關閉介面稍後恢復。');
  })); root.append(confirm);
  const cancel = node('button','返回修改人物'); cancel.addEventListener('click',() => { review=null; showReview(); void sync(); }); root.append(cancel);
  expiryTimer = setTimeout(() => { review=null; showReview(); status('確認內容已到期，請重新查看後確認。',true); }, Math.max(0,new Date(review.reviewExpiresAt).getTime()-Date.now()));
}
function renderSources() {
  $('outfit').textContent = `${data.planName}／${data.kimonoName}${data.isDemo ? '（示範商品）' : ''}`;
  $('usage').textContent = `MCP 今日剩餘 ${data.usage.mcp.remaining}／${data.usage.mcp.limit} 次；日本午夜重設。網站額度分開。`;
  const root = $('sources'); root.replaceChildren();
  const choices = [...data.models.map(m => ({id:m.id,source:'MODEL',name:m.name,warning:m.warning})), ...data.photos.map((p,i) => ({id:p.photoId,source:'SELF',name:`本人照片 ${i+1}`,warning:p.status==='READY'?'照片已通過檢查':'照片仍需檢查'}))];
  for (const value of choices) {
    const card = node('article'); card.append(picture(value.id,value.name),node('h3',value.name));
    if (value.warning) card.append(node('p',value.warning,'muted'));
    const choose = node('button',source?.id===value.id?'已選擇 ✓':'選擇此人物',source?.id===value.id?'primary':'');
    choose.addEventListener('click',() => run(async () => { source={id:value.id,source:value.source}; review=null; showReview(); renderSources(); await sync(); status('已選人物；尚未生成或扣額度。'); }));
    card.append(choose); root.append(card);
  }
  if (!data.photos.length) root.append(node('p','照片庫目前沒有有效本人照片，可使用模特兒，或按「新增本人照片」。','muted'));
}
function renderJobs() {
  const root = $('results');
  const images = new Map([...root.querySelectorAll('img')].map(img => [img.dataset.mediaId,img]));
  root.replaceChildren();
  for (const j of [...jobs.values()].sort((a,b)=>b.createdAt.localeCompare(a.createdAt))) {
    const card = node('article'); const expired=j.expiresAt && Date.parse(j.expiresAt)<=Date.now();
    card.append(node('h3',j.kimonoName || (j.kimonoId===data?.kimonoId?data.kimonoName:`和服 ${j.kimonoId}`)),node('p',expired?'圖片已到期':labels[j.status]),node('p',`任務：${j.jobId}`,'muted'));
    card.append(node('p',j.modelId ? `人物：${data?.models.find(m=>m.id===j.modelId)?.name || '商店模特兒'}（${j.modelId.slice(0,8)}）` : `人物：本人照片（${j.photoId?.slice(0,8)}）`,'muted'));
    if (j.status==='SUCCEEDED' && !expired) card.append(picture(j.jobId,'AI 和服試穿示意',j.expiresAt,images.get(j.jobId)));
    if (j.expiresAt) card.append(node('p',`到期：${new Date(j.expiresAt).toLocaleString('zh-TW',{timeZone:'Asia/Tokyo'})}（日本時間）`,'muted'));
    if (j.failure) card.append(node('p',j.failure.message,'muted'));
    root.append(card);
  }
  if (!jobs.size) root.append(node('p','尚無本次試穿結果。','muted'));
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (![...jobs.values()].some(active)) return;
  pollTimer=setTimeout(() => { if (busy) { schedulePoll(); return; } void run(async () => {
    for (const j of [...jobs.values()].filter(active)) { const updated=await call('get_try_on_job',{jobId:j.jobId}); jobs.set(updated.jobId,updated); } renderJobs(); await sync(); schedulePoll();
  }); },5000);
}
async function refresh() {
  const updated=await call('show_try_on',{planId:data.planId,kimonoId:data.kimonoId,conversationId:data.conversationId});
  data=updated; if (source && ![...data.models.map(m=>m.id),...data.photos.map(p=>p.photoId)].includes(source.id)) { source=null; review=null; showReview(); }
  for (const j of data.jobs) jobs.set(j.jobId,j); if (data.activeJob) jobs.set(data.activeJob.jobId,data.activeJob);
  renderSources(); renderJobs(); schedulePoll(); await sync(); status('已刷新人物照片、額度及本次任務。');
}
function clearPhotoFile() {
  selectedFile=null; pendingUpload=null; $('photo-file').value=''; $('photo-file-name').textContent='';
  $('photo-preview').hidden=true; $('photo-preview').removeAttribute('src'); $('photo-consent').checked=false;
}
$('add-photo').addEventListener('click',()=>void run(async()=>{
  photoConsent=await call('get_photo_upload_consent',{});
  clearPhotoFile(); $('photo-consent-text').textContent=photoConsent.text;
  $('photo-limits').textContent=`${photoConsent.formats.join('／')}，最多 ${Math.floor(photoConsent.maxBytes/1024/1024)} MiB，照片長邊 ${photoConsent.minLongEdge}～${photoConsent.maxLongEdge} 像素。`;
  $('photo-upload').hidden=false; status('請選擇本人照片並閱讀處理說明；尚未上傳。');
}));
$('photo-file').addEventListener('change',()=>void run(async()=>{
  const file=$('photo-file').files?.[0]; clearPhotoFile();
  if(!file)return;
  const type=file.type || (/\.heic$/i.test(file.name)?'image/heic':/\.heif$/i.test(file.name)?'image/heif':'');
  if(!['image/jpeg','image/png','image/heic','image/heif'].includes(type))throw new Error('請選擇 JPEG、PNG 或 HEIC／HEIF 照片。');
  if(!file.size || file.size>photoConsent.maxBytes)throw new Error('照片大小必須大於 0 且不超過 10 MiB。');
  selectedFile={file,contentType:type}; $('photo-file-name').textContent=`${file.name}（${(file.size/1024/1024).toFixed(2)} MiB）`;
  if(['image/jpeg','image/png'].includes(type) && typeof FileReader!=='undefined') {
    const preview=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>resolve(null);reader.readAsDataURL(file);});
    if(preview){$('photo-preview').src=preview;$('photo-preview').hidden=false;}
  } else $('photo-file-name').textContent+='；此格式可能無法在客戶端預覽，將由後端檢查。';
  status('已選擇本機檔案；勾選同意並按上傳前，不會傳送照片。');
}));
$('photo-consent').addEventListener('change',controls);
$('cancel-photo').addEventListener('click',()=>{clearPhotoFile();$('photo-upload').hidden=true;controls();status('已取消新增照片；原有選擇不受影響。');});
$('submit-photo').addEventListener('click',()=>void run(async()=>{
  if(!selectedFile || !$('photo-consent').checked)throw new Error('請先選擇照片並勾選處理同意。');
  if(pendingUpload && Date.parse(pendingUpload.expiresAt)<=Date.now())pendingUpload=null;
  if(!pendingUpload) {
    status('正在準備本次照片上傳…');
    const result=await app.callServerTool({name:'create_photo_upload',arguments:{planId:data.planId,kimonoId:data.kimonoId,conversationId:data.conversationId,consentAccepted:true,consentVersion:photoConsent.version,contentType:selectedFile.contentType,size:selectedFile.file.size}});
    const receipt=unpack(result), grant=result._meta?.upload;
    let destination;try{destination=new URL(grant?.url);}catch{}
    if(!grant || destination?.protocol!=='https:' || destination.username || destination.password)throw new Error('此客戶端未提供可用的上傳權限，請改用官網備援。');
    pendingUpload={...receipt,grant,transferred:false};
  }
  if(!pendingUpload.transferred) {
    status('正在上傳照片，請保持此介面開啟…');
    const form=new FormData();for(const [key,value] of Object.entries(pendingUpload.grant.fields))form.append(key,value);
    form.append('file',selectedFile.file,'photo');
    // An opaque response is not proof of receipt; completion checks S3 below.
    await transferPhoto(pendingUpload,form);
    pendingUpload.transferred=true;
  }
  status('正在檢查照片格式與人物，尚未生成…');
  let result;
  try { result=await call('complete_photo_upload',{sessionId:pendingUpload.sessionId,photoId:pendingUpload.photoId},{timeout:90000}); }
  catch(error){if(error.code==='PHOTO_UPLOAD_MISSING')pendingUpload.transferred=false;throw error;}
  if(result.photo.status!=='READY') {
    const message=result.photo.issues.map(i=>i.message).join('；') || '照片未通過檢查，請重新選擇。';
    clearPhotoFile();throw new Error(message);
  }
  const photoId=result.photo.photoId;clearPhotoFile();$('photo-upload').hidden=true;
  review=null;showReview();await refresh();source={id:photoId,source:'SELF'};renderSources();await sync();
  status('本人照片已通過檢查並加入照片庫，已選為本次人物。尚未生成或扣額度。');
}));
$('refresh').addEventListener('click',()=>void run(refresh));
$('recover').addEventListener('click',()=>void run(async()=>{ const value=await call('get_try_on_jobs',{conversationId:data.conversationId}); for(const j of value.jobs) jobs.set(j.jobId,j); renderJobs(); schedulePoll(); await sync(); status('已更新本次任務與有效圖片網址。'); }));
function uploadUrl() {
  let url;
  try { url=new URL(data.uploadPageUrl); } catch { throw new Error('官網入口尚未正確設定，請管理者設定 MCP 的 KINUTABI_WEB_BASE_URL 並重啟服務。'); }
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password) throw new Error('官網入口無效，請聯絡管理者。');
  return url.href;
}
$('upload').addEventListener('click',()=>void run(async()=>{
  const url=uploadUrl();
  const help=$('upload-help'); help.hidden=false; help.textContent=`若官網未開啟，可按「請 AI 在 Codex 開啟官網」，或複製此網址至瀏覽器：${url}`;
  $('upload-assist').hidden=false;
  if (!app.getHostCapabilities()?.openLinks) {
    websiteOpen={status:'unsupported'}; await sync();
    status('此客戶端未提供直接開啟連結功能，請使用下方的「請 AI 在 Codex 開啟官網」。',true); return;
  }
  status('正在請客戶端開啟官網…');
  try {
    const result=await app.openLink({url},{timeout:8000});
    if(result?.isError) {
      websiteOpen={status:'rejected'}; await sync();
      status('客戶端拒絕或無法開啟官網，請使用下方的備援按鈕。',true); return;
    }
    websiteOpen={status:'accepted'}; await sync();
    status('客戶端已接受開啟要求；若未出現官網，請按下方備援按鈕。完成上傳及同意後，返回刷新照片庫。');
  } catch(error) {
    websiteOpen={status:error.code===-32001?'timeout':'failed',code:typeof error.code==='number'?error.code:undefined}; await sync();
    status(error.code===-32001?'客戶端未在 8 秒內回應，請使用下方備援按鈕。':'客戶端開啟連結失敗，請使用下方備援按鈕。',true);
  }
}));
$('upload-assist').addEventListener('click',()=>void run(async()=>{
  const url=uploadUrl();
  const result=await app.sendMessage({role:'user',content:[{type:'text',text:`請在 Codex 的瀏覽器面板開啟 KINU TABI 官網新增照片頁：${url}。只開啟網頁，不上傳照片或執行生成。`}]});
  if(result?.isError) throw new Error('客戶端未能送出開啟要求，請複製下方官網網址至瀏覽器。');
  status('已請 AI 開啟官網。請自行登入、上傳並完成同意，再返回刷新照片庫。');
}));
$('prepare').addEventListener('click',()=>void run(async()=>{ if(!source)throw new Error('請先選擇人物。'); review=await call('prepare_try_on',{planId:data.planId,kimonoId:data.kimonoId,conversationId:data.conversationId,source:source.source,...(source.source==='MODEL'?{modelId:source.id}:{photoId:source.id})}); showReview(); await sync(); status('請查看確認內容；目前尚未生成。'); }));
$('skip').addEventListener('click',()=>void run(async()=>{ review=null; showReview(); await sync(); status('已略過本次試穿，選款不受影響；已確認的後端任務仍會繼續。'); }));
app.ontoolresult=result=>{
  try {
    const value=unpack(result);
    if(value.view==='tryOnSources'){
      if(data && (data.planId!==value.planId || data.kimonoId!==value.kimonoId)){clearPhotoFile();$('photo-upload').hidden=true;}
      data=value; for(const j of data.jobs) jobs.set(j.jobId,j); if(data.activeJob)jobs.set(data.activeJob.jobId,data.activeJob);renderSources();renderJobs();schedulePoll();void sync();
    }
    status('可選擇人物，或略過試穿。'); controls();
  } catch(e){status(e.message,true);}
};
if(window.parent===window)status('請在支援 MCP Apps 的 AI 客戶端呼叫 show_try_on。',true);
else app.connect().then(()=>{connected=true;controls();}).catch(()=>status('無法連接 MCP Apps，請改用文字工具查詢。',true));
