import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { test } from 'node:test';

// Exercise the real UI handlers with a small DOM, SDK stub and virtual clock.
// No browser, member credential, database or paid generation is used.
const script=(await readFile(new URL('../ui/upload-diagnostics.mjs',import.meta.url),'utf8')).replace('export async function','async function') + '\n' +
  (await readFile(new URL('../ui/try-on.mjs',import.meta.url),'utf8')).replace(/^import .*?;\r?\n/gm,'');
function setup() {
  class Element {
    constructor(tag) { this.tagName=tag; this.children=[]; this.dataset={}; this.listeners={}; this.textContent=''; this.complete=true; this.naturalWidth=100; }
    append(...children) { for (const child of children) { if(child.parent) child.parent.children=child.parent.children.filter(c=>c!==child); child.parent=this; this.children.push(child); } }
    replaceChildren(...children) { for(const child of this.children) child.parent=null; this.children=[]; this.append(...children); }
    replaceWith(child) { const parent=this.parent; if(!parent)return; const index=parent.children.indexOf(this); parent.children[index]=child; child.parent=parent; this.parent=null; }
    addEventListener(type,handler) { this.listeners[type]=handler; }
    removeAttribute(name) { delete this[name]; }
    querySelectorAll(tag) { return this.children.flatMap(child=>[...(child.tagName===tag?[child]:[]),...child.querySelectorAll(tag)]); }
    get isConnected() { return Boolean(this.root || this.parent?.isConnected); }
  }
  const ids=Object.fromEntries(['status','outfit','usage','sources','results','review','prepare','recover','upload','upload-help','upload-assist','refresh','skip','add-photo','photo-upload','photo-file','photo-file-name','photo-preview','photo-consent','photo-consent-text','photo-limits','submit-photo','cancel-photo'].map(id=>{const el=new Element(['prepare','recover','upload','upload-assist','refresh','skip','add-photo','submit-photo','cancel-photo'].includes(id)?'button':'div');el.root=true;return [id,el];}));
  const calls=[], links=[], messages=[], contexts=[], transfers=[], timers=new Map(); let clock=Date.now(), timerId=0, sdk;
  class Clock extends Date { constructor(...args) { super(...(args.length?args:[clock])); } static now(){return clock;} }
  const job={jobId:'job-1',status:'SUCCEEDED',kimonoId:'kimono-1',modelId:'model-1',createdAt:new Date(clock).toISOString(),expiresAt:new Date(clock+3600000).toISOString()};
  const data={view:'tryOnSources',planId:'plan-1',kimonoId:'kimono-1',conversationId:'conversation-1',planName:'測試方案',kimonoName:'測試和服',usage:{mcp:{remaining:2,limit:3}},models:[],photos:[],jobs:[job],activeJob:null,uploadPageUrl:'http://localhost:5173/try-on?plan=plan-1'};
  const result=(url='https://private.example/result?original')=>({structuredContent:structuredClone(data),_meta:{media:{'job-1':url}}});
  class App {
    constructor(){sdk=this;}
    async connect(){}
    getHostCapabilities(){return this.capabilities ?? {openLinks:{}};}
    async updateModelContext(value){contexts.push(value);}
    async openLink(value){links.push(value);if(this.openError)throw this.openError;return this.openResult || {};}
    async sendMessage(value){messages.push(value);return {};}
    async callServerTool(value){
      calls.push(value);if(this.handleTool)return this.handleTool(value);
      if(value.name==='get_photo_upload_consent')return {structuredContent:{view:'photoConsent',version:'consent-v1',text:'本人照片處理說明',maxBytes:10485760,maxPhotos:3,minLongEdge:1200,maxLongEdge:6000,formats:['JPEG','PNG','HEIC']}};
      if(value.name==='create_photo_upload')return {structuredContent:{view:'photoUpload',sessionId:'session-upload',photoId:'photo-upload',expiresAt:new Date(clock+300000).toISOString()},_meta:{upload:{url:'https://private.example/',fields:{key:'private/try-on/uploads/test',policy:'signed-upload-policy'}}}};
      if(value.name==='complete_photo_upload'){
        if(this.validationUnavailable)return {isError:true,content:[{type:'text',text:'人物檢查暫時無法使用，請重試。'}],structuredContent:{error:{code:'PHOTO_VALIDATION_UNAVAILABLE'}}};
        data.photos=[{photoId:'photo-upload',status:'READY'}];return {structuredContent:{view:'photoUploaded',photo:{photoId:'photo-upload',status:'READY',issues:[]}}};
      }
      if(value.name==='show_try_on')return result();
      assert.equal(value.name,'get_try_on_jobs');return {structuredContent:{view:'tryOnJobs',jobs:[job]},_meta:{media:{'job-1':'https://private.example/result?refreshed'}}};
    }
  }
  class FileReader { readAsDataURL(){this.result='data:image/jpeg;base64,LOCAL_PREVIEW';this.onload();} }
  class FormData { constructor(){this.fields=[];} append(...entry){this.fields.push(entry);} }
  const context=vm.createContext({App,URL,performance:{now:()=>clock},Date:Clock,FileReader,FormData,AbortSignal,fetch:async(url,options)=>{transfers.push({url,options});if(sdk.transferError)throw sdk.transferError;return {type:'opaque',status:0};},document:{addEventListener(){},removeEventListener(){},getElementById:id=>ids[id],createElement:tag=>new Element(tag),createTextNode:text=>Object.assign(new Element('#text'),{textContent:text}),querySelectorAll:tag=>Object.values(ids).filter(el=>el.tagName===tag)},window:{parent:{}},setTimeout:(fn,delay)=>{if(delay===100){queueMicrotask(fn);return 0;}timers.set(++timerId,{fn,at:clock+delay});return timerId;},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(script,context);
  const flush=async()=>{for(let i=0;i<64;i++)await Promise.resolve();};
  const deliver=async()=>{await flush();sdk.ontoolresult(result());await flush();};
  const click=async id=>{ids[id].listeners.click();await flush();};
  const change=async id=>{ids[id].listeners.change();await flush();};
  const advance=async ms=>{const end=clock+ms;for(;;){const next=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;clock=next[1].at;timers.delete(next[0]);next[1].fn();await flush();}clock=end;};
  return {ids,data,job,calls,links,messages,contexts,transfers,sdk,deliver,click,change,advance};
}

test('upload opens the absolute website URL; malformed and host-rejected links give actionable feedback',async()=>{
  const ui=setup();await ui.deliver();await ui.click('upload');
  assert.equal(ui.links[0].url,ui.data.uploadPageUrl);
  ui.sdk.openResult={isError:true};await ui.click('upload');
  assert.match(ui.ids.status.textContent,/客戶端拒絕或無法開啟官網/);
  assert.ok(ui.ids['upload-help'].textContent.includes(ui.data.uploadPageUrl));
  ui.data.uploadPageUrl='/try-on';await ui.deliver();await ui.click('upload');
  assert.match(ui.ids.status.textContent,/KINUTABI_WEB_BASE_URL/);
  assert.ok(!ui.ids.status.textContent.includes('Invalid URL'));
  assert.equal(ui.links.length,2);
});

test('unsupported host offers an explicit AI open request without calling openLink',async()=>{
  const ui=setup();ui.sdk.capabilities={};await ui.deliver();await ui.click('upload');
  assert.equal(ui.links.length,0);assert.match(ui.ids.status.textContent,/未提供直接開啟連結/);
  assert.equal(ui.ids['upload-assist'].hidden,false);assert.equal(ui.messages.length,0);
  assert.ok(ui.contexts.at(-1).content[0].text.includes('"status":"unsupported"'));
  await ui.click('upload-assist');
  assert.equal(ui.messages.length,1);assert.ok(ui.messages[0].content[0].text.includes(ui.data.uploadPageUrl));
  assert.ok(ui.messages[0].content[0].text.includes('不上傳照片或執行生成'));
  assert.equal(ui.calls.length,0);
});

test('host acceptance is distinguished from page opening, and timeouts remain actionable',async()=>{
  const ui=setup();await ui.deliver();await ui.click('upload');
  assert.match(ui.ids.status.textContent,/已接受開啟要求/);
  assert.ok(ui.contexts.at(-1).content[0].text.includes('"status":"accepted"'));
  ui.sdk.openError={code:-32001};await ui.click('upload');
  assert.match(ui.ids.status.textContent,/8 秒內回應/);
  assert.ok(ui.contexts.at(-1).content[0].text.includes('"status":"timeout"'));
});

test('loaded result survives URL TTL and rerender, then disappears at actual image expiry',async()=>{
  const ui=setup();await ui.deliver();const image=ui.ids.results.querySelectorAll('img')[0];
  assert.ok(image.isConnected);
  await ui.advance(121000);assert.equal(ui.ids.results.querySelectorAll('img')[0],image);
  await ui.deliver();assert.equal(ui.ids.results.querySelectorAll('img')[0],image);
  await ui.advance(3600000);assert.equal(ui.ids.results.querySelectorAll('img').length,0);
  assert.ok(ui.ids.results.children[0].children.some(el=>el.textContent==='圖片已到期'));
  assert.equal(ui.calls.length,0);
});

test('failed image can obtain a new URL through read-only job recovery without generating',async()=>{
  const ui=setup();await ui.deliver();const image=ui.ids.results.querySelectorAll('img')[0];
  image.naturalWidth=0;image.listeners.error();
  assert.equal(ui.ids.results.querySelectorAll('img').length,0);
  await ui.click('recover');
  assert.equal(ui.ids.results.querySelectorAll('img')[0].src,'https://private.example/result?refreshed');
  assert.deepEqual(ui.calls.map(c=>c.name),['get_try_on_jobs']);
  assert.equal(ui.data.usage.mcp.remaining,2);
});

async function selectPhoto(ui) {
  await ui.deliver();await ui.click('add-photo');
  ui.ids['photo-file'].files=[{name:'private-person.jpg',size:4096,type:'image/jpeg'}];await ui.change('photo-file');
}

test('photo selection stays local until consent, then opaque upload is verified and added without generation',async()=>{
  const ui=setup();await selectPhoto(ui);
  assert.equal(ui.transfers.length,0);assert.equal(ui.ids['submit-photo'].disabled,true);
  await ui.click('submit-photo');assert.equal(ui.calls.filter(c=>c.name==='create_photo_upload').length,0);
  ui.ids['photo-consent'].checked=true;await ui.change('photo-consent');await ui.click('submit-photo');
  assert.equal(ui.transfers.length,1);assert.equal(ui.transfers[0].options.mode,'no-cors');assert.equal(ui.transfers[0].options.credentials,'omit');
  assert.equal(ui.transfers[0].options.body.fields.at(-1)[2],'photo');
  assert.deepEqual(ui.calls.map(c=>c.name),['get_photo_upload_consent','create_photo_upload','complete_photo_upload','show_try_on']);
  assert.match(ui.ids.status.textContent,/照片已通過檢查/);assert.equal(ui.data.photos[0].photoId,'photo-upload');
  const contextText=JSON.stringify(ui.contexts),toolText=JSON.stringify(ui.calls);
  for(const secret of ['private-person.jpg','LOCAL_PREVIEW','signed-upload-policy']){assert.ok(!contextText.includes(secret));assert.ok(!toolText.includes(secret));}
});

test('failed transfer retries its original grant and never creates another upload or generation',async()=>{
  const ui=setup();await selectPhoto(ui);ui.ids['photo-consent'].checked=true;ui.sdk.transferError=new Error('network unavailable');
  await ui.click('submit-photo');assert.equal(ui.calls.filter(c=>c.name==='complete_photo_upload').length,0);assert.equal(ui.ids['submit-photo'].textContent,'重試本次上傳');
  ui.sdk.transferError=null;await ui.click('submit-photo');
  assert.equal(ui.calls.filter(c=>c.name==='create_photo_upload').length,1);assert.equal(ui.transfers.length,2);
  assert.match(ui.ids.status.textContent,/照片已通過檢查/);
});

test('an opaque response alone never adds a rejected photo to the library',async()=>{
  const ui=setup();await selectPhoto(ui);ui.ids['photo-consent'].checked=true;
  const original=ui.sdk.callServerTool.bind(ui.sdk);
  ui.sdk.callServerTool=async value=>value.name==='complete_photo_upload'?{structuredContent:{view:'photoUploaded',photo:{photoId:'photo-upload',status:'REJECTED',issues:[{code:'NO_PERSON',message:'找不到人物，請重新選擇照片。'}]}}}:original(value);
  await ui.click('submit-photo');
  assert.equal(ui.transfers.length,1);assert.equal(ui.data.photos.length,0);assert.match(ui.ids.status.textContent,/找不到人物/);
  assert.ok(!ui.calls.some(c=>c.name==='show_try_on'||c.name==='confirm_try_on'));
});

test('validation outage retries the original receipt without another transfer or upload reservation',async()=>{
  const ui=setup();await selectPhoto(ui);ui.ids['photo-consent'].checked=true;ui.sdk.validationUnavailable=true;
  await ui.click('submit-photo');assert.equal(ui.data.photos.length,0);assert.equal(ui.ids['submit-photo'].textContent,'重試照片檢查');
  ui.sdk.validationUnavailable=false;await ui.click('submit-photo');
  assert.equal(ui.transfers.length,1);assert.equal(ui.calls.filter(c=>c.name==='create_photo_upload').length,1);
  const completes=ui.calls.filter(c=>c.name==='complete_photo_upload');assert.equal(completes.length,2);assert.deepEqual(completes[0].arguments,completes[1].arguments);
  assert.match(ui.ids.status.textContent,/照片已通過檢查/);
});

test('unsupported and oversized files do not leave the client',async()=>{
  const ui=setup();await ui.deliver();await ui.click('add-photo');
  for(const file of [{name:'large.jpg',size:10485761,type:'image/jpeg'},{name:'document.txt',size:100,type:'text/plain'}]){
    ui.ids['photo-file'].files=[file];await ui.change('photo-file');assert.equal(ui.ids['submit-photo'].disabled,true);
  }
  assert.equal(ui.transfers.length,0);assert.deepEqual(ui.calls.map(c=>c.name),['get_photo_upload_consent']);
});
