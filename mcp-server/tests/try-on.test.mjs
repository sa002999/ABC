import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer as httpServer } from 'node:http';
import { test } from 'node:test';
import { Client } from '@modelcontextprotocol/client';
import { InMemoryTransport } from '@modelcontextprotocol/server';
import { createServer, TRY_ON_URI } from '../server.mjs';
import { loadConfig } from '../config.mjs';

test('try-on requires member auth, explicit confirmation, UI-only private media and restricted image CSP', async () => {
  const id='30000000-0000-4000-8000-000000000012';
  const bucket='https://private-test.s3.amazonaws.com';
  let confirmations=0, forwarded, uploadPageUrl='/try-on?plan='+id;
  const job={jobId:id,source:'MCP',status:'SUCCEEDED',planId:id,kimonoId:id,photoId:null,modelId:id,createdAt:new Date().toISOString(),expiresAt:new Date(Date.now()+120000).toISOString(),imageUrl:bucket+'/private/result.jpg?signature=private',imageUrlExpiresIn:120,failure:null};
  const upstream=httpServer(async(req,res)=>{
    res.setHeader('Content-Type','application/json');
    if(req.url==='/api/mcp/try-on/media-config'){res.end(JSON.stringify({imageOrigins:[bucket]}));return;}
    assert.equal(req.headers.authorization,'Bearer member-credential');
    let raw='';for await(const chunk of req)raw+=chunk;forwarded=raw?JSON.parse(raw):undefined;
    if(req.url.endsWith('/sources'))res.end(JSON.stringify({view:'tryOnSources',...forwarded,planName:{'zh-Hant':'方案'},kimonoName:{'zh-Hant':'和服'},conversationId:id,isDemo:true,usage:{mcp:{remaining:3}},models:[{id,name:{'zh-Hant':'模特兒'},role:'FEMALE',previewUrl:'/api/models/'+id+'/preview'}],photos:[{photoId:id,previewUrl:bucket+'/private/photo.webp?signature=private'}],jobs:[job],activeJob:null,uploadPageUrl}));
    else if(req.url.endsWith('/prepare'))res.end(JSON.stringify({view:'tryOnReview',reviewId:id,reviewExpiresAt:new Date(Date.now()+600000).toISOString(),planName:{'zh-Hant':'方案'},kimonoName:{'zh-Hant':'和服'},usage:{mcp:{remaining:3}},source:'MODEL',modelName:{'zh-Hant':'模特兒'}}));
    else if(req.url.endsWith('/confirm')){confirmations++;res.end(JSON.stringify({view:'tryOnJob',...job}));}
    else {res.writeHead(404);res.end('{}');}
  }).listen(0,'127.0.0.1');await once(upstream,'listening');
  const config={...loadConfig({KINUTABI_API_BASE_URL:`http://127.0.0.1:${upstream.address().port}`,KINUTABI_WEB_BASE_URL:'http://localhost:5173'}),memberAuthorization:'Bearer member-credential'};
  const server=createServer(config),client=new Client({name:'try-on-test',version:'1'});
  const [a,b]=InMemoryTransport.createLinkedPair();await server.connect(b);await client.connect(a);
  try {
    const source=await client.callTool({name:'show_try_on',arguments:{planId:id,kimonoId:id}});
    assert.equal(source.isError,undefined);assert.equal(source.structuredContent.kimonoName,'和服');
    assert.equal(source.structuredContent.uploadPageUrl,`http://localhost:5173/try-on?plan=${id}`);
    for (uploadPageUrl of ['', 'https://untrusted.example/upload']) {
      const sources=await client.callTool({name:'show_try_on',arguments:{planId:id,kimonoId:id}});
      assert.equal(sources.structuredContent.uploadPageUrl,`http://localhost:5173/try-on?plan=${id}`);
    }
    assert.ok(!JSON.stringify(source.structuredContent).includes('signature=private'));
    assert.equal(source._meta.media[id],job.imageUrl);
    const review=await client.callTool({name:'prepare_try_on',arguments:{planId:id,kimonoId:id,source:'MODEL',modelId:id}});
    assert.equal(review.structuredContent.reviewId,id);assert.equal(confirmations,0);
    for(const invalid of [{reviewId:id,confirmed:false},{reviewId:id,confirmed:true,channel:'WEBSITE'},{reviewId:id,confirmed:true,userId:id}])assert.equal((await client.callTool({name:'confirm_try_on',arguments:invalid})).isError,true);
    assert.equal(confirmations,0);
    const result=await client.callTool({name:'confirm_try_on',arguments:{reviewId:id,confirmed:true}});
    assert.equal(result.structuredContent.status,'SUCCEEDED');assert.equal(confirmations,1);
    assert.deepEqual(forwarded,{reviewId:id,confirmed:true});assert.equal(result._meta.media[id],job.imageUrl);
    const resource=await client.readResource({uri:TRY_ON_URI});
    assert.ok(resource.contents[0]._meta.ui.csp.resourceDomains.includes(bucket));assert.deepEqual(resource.contents[0]._meta.ui.csp.connectDomains,[bucket]);
    assert.ok(resource.contents[0].text.includes('aria-label="本次生成確認"'));
  } finally {await client.close();await server.close();await new Promise(resolve=>upstream.close(resolve));}
});

test('website origin is independent from the API and rejects invalid upload destinations', () => {
  assert.equal(loadConfig({KINUTABI_API_BASE_URL:'https://api.example.com',KINUTABI_WEB_BASE_URL:'https://www.example.com/'}).webOrigin,'https://www.example.com');
  for (const value of ['/try-on', 'http://remote.example.com', 'https://user:secret@example.com', 'https://example.com/try-on', 'https://example.com?next=other']) {
    assert.throws(()=>loadConfig({KINUTABI_WEB_BASE_URL:value}));
  }
});

test('photo upload grants are app-only metadata, reject unsafe destinations and identity arguments, and completion never generates',async()=>{
  const id='30000000-0000-4000-8000-000000000012',bucket='https://private-test.s3.amazonaws.com';
  let uploadOrigin=bucket,requests=0;
  const upstream=httpServer(async(req,res)=>{
    res.setHeader('Content-Type','application/json');
    if(req.url.endsWith('/media-config')){res.end(JSON.stringify({imageOrigins:[bucket]}));return;}
    requests++;assert.equal(req.headers.authorization,'Bearer member-credential');
    let raw='';for await(const c of req)raw+=c;
    if(req.url.endsWith('/photo-consent'))res.end(JSON.stringify({view:'photoConsent',version:'consent-v1',text:'照片同意說明',maxBytes:10485760,maxPhotos:3,minLongEdge:1200,maxLongEdge:6000,formats:['JPEG','PNG','HEIC']}));
    else if(req.url.endsWith('/photo-uploads'))res.end(JSON.stringify({view:'photoUpload',sessionId:id,photoId:id,expiresAt:new Date(Date.now()+300000).toISOString(),upload:{method:'POST',uploadUrl:uploadOrigin+'/',fields:{key:'private/try-on/uploads/test/photo','Content-Type':'image/jpeg',policy:'PRIVATE_SIGNED_POLICY'},photoId:id,expiresAt:new Date(Date.now()+300000).toISOString()}}));
    else if(req.url.endsWith('/photo-uploads/complete'))res.end(JSON.stringify({view:'photoUploaded',photo:{photoId:id,status:'READY',issues:[],width:1200,height:1800,qualityStatus:'PASSED',previewUrl:bucket+'/private/photo?signature=private',previewExpiresIn:120}}));
    else{assert.fail('Unexpected generation or API request');}
  }).listen(0,'127.0.0.1');await once(upstream,'listening');
  const config={...loadConfig({KINUTABI_API_BASE_URL:`http://127.0.0.1:${upstream.address().port}`}),memberAuthorization:'Bearer member-credential'};
  const server=createServer(config),client=new Client({name:'photo-upload-test',version:'1'});
  const [a,b]=InMemoryTransport.createLinkedPair();await server.connect(b);await client.connect(a);
  const input={planId:id,kimonoId:id,consentAccepted:true,consentVersion:'consent-v1',contentType:'image/jpeg',size:4096};
  try{
    const consent=await client.callTool({name:'get_photo_upload_consent',arguments:{}});assert.equal(consent.structuredContent.version,'consent-v1');
    const before=requests;
    for(const invalid of [{...input,consentAccepted:false},{...input,size:10485761},{...input,userId:id},{...input,token:'private-token'}])assert.equal((await client.callTool({name:'create_photo_upload',arguments:invalid})).isError,true);
    assert.equal(requests,before);
    const grant=await client.callTool({name:'create_photo_upload',arguments:input});assert.ok(!grant.isError);
    assert.equal(grant._meta.upload.fields.policy,'PRIVATE_SIGNED_POLICY');
    assert.ok(!JSON.stringify(grant.structuredContent).includes('PRIVATE_SIGNED_POLICY'));assert.ok(!JSON.stringify(grant.content).includes('private/try-on/uploads'));
    uploadOrigin='https://untrusted.example';assert.equal((await client.callTool({name:'create_photo_upload',arguments:input})).structuredContent.error.code,'INVALID_UPLOAD_DESTINATION');
    const completed=await client.callTool({name:'complete_photo_upload',arguments:{sessionId:id,photoId:id}});
    assert.equal(completed.structuredContent.photo.status,'READY');assert.ok(!JSON.stringify(completed).includes('signature=private'));
  }finally{await client.close();await server.close();await new Promise(resolve=>upstream.close(resolve));}
});
