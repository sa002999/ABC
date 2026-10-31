// Controlled UI fixture: fake API, synthetic credential, no database/Vertex writes.
import { createServer } from 'node:http';
import { once } from 'node:events';
import express from 'express';
import { createHttpApp } from '../main.mjs';
import { addPreviewRoutes } from '../preview.mjs';
import { loadConfig } from '../config.mjs';
const id='30000000-0000-4000-8000-000000000012';
const models=await fetch('http://127.0.0.1:8000/api/models').then(r=>r.json());
const model=models.data[0];
const image='http://127.0.0.1:8000'+model.previewUrl;
let confirmed=false;
const timestamp=new Date().toISOString();
const job=()=>({view:'tryOnJob',jobId:id,source:'MCP',status:confirmed?'SUCCEEDED':'QUEUED',planId:id,kimonoId:id,kimonoName:'測試和服（模擬結果）',photoId:null,modelId:model.id,createdAt:timestamp,expiresAt:new Date(Date.now()+600000).toISOString(),imageUrl:confirmed?image:null,imageUrlExpiresIn:120,failure:null});
const api=createServer(async(req,res)=>{
  res.setHeader('Content-Type','application/json');
  let raw='';for await(const c of req)raw+=c;const body=raw?JSON.parse(raw):{};
  if(req.url==='/api/mcp/member')res.end(JSON.stringify({authenticated:true,channel:'MCP'}));
  else if(req.url.endsWith('/media-config'))res.end(JSON.stringify({imageOrigins:[]}));
  else if(req.url.endsWith('/sources'))res.end(JSON.stringify({view:'tryOnSources',planId:id,kimonoId:id,conversationId:id,planName:'UI 驗證方案',kimonoName:'測試和服',isDemo:true,
    models:[{...model,previewUrl:image}],photos:[],usage:{mcp:{limit:3,remaining:confirmed?2:3}},jobs:confirmed?[job()]:[],activeJob:null,uploadPageUrl:'http://127.0.0.1:8000/try-on',notice:'模擬 API，無付費 AI 呼叫'}));
  else if(req.url.endsWith('/prepare'))res.end(JSON.stringify({view:'tryOnReview',reviewId:id,conversationId:id,planId:id,kimonoId:id,planName:'UI 驗證方案',kimonoName:'測試和服',source:'MODEL',modelId:model.id,modelName:model.name,usage:{mcp:{remaining:3}},reviewExpiresAt:new Date(Date.now()+600000).toISOString(),isDemo:true,notice:'測試：確認後模擬使用一次額度；完成當日日本午夜到期。實際未呼叫模型。'}));
  else if(req.url.endsWith('/confirm')){confirmed=true;res.end(JSON.stringify({...job(),usage:{mcp:{limit:3,remaining:2}}}));}
  else if(req.url.includes('/jobs'))res.end(JSON.stringify(req.url.split('?')[0].endsWith('/jobs')?{view:'tryOnJobs',jobs:confirmed?[job()]:[],notice:'模擬任務'}:job()));
  else {res.writeHead(404);res.end('{}');}
}).listen(0,'127.0.0.1');await once(api,'listening');
const config=loadConfig({KINUTABI_API_BASE_URL:`http://127.0.0.1:${api.address().port}`,KINUTABI_IMAGE_ORIGINS:'http://127.0.0.1:8000',PORT:'3003'});
const app=express();
// Synthetic credential is valid only for the mock API above, never a real member.
app.use((req,_res,next)=>{if(req.path==='/mcp')req.headers.authorization='Bearer kt_mcp_'+'t'.repeat(43);next();});
const mcp=createHttpApp(config);addPreviewRoutes(mcp,config);app.use(mcp);
const listener=app.listen(3003,'127.0.0.1',()=>console.log(`MOCK UI ONLY: http://127.0.0.1:3003/_dev?view=try-on&plan=${id}&kimono=${id}`));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{listener.close();api.close();process.exit(0);});
