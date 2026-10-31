import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createServer as httpServer} from 'node:http';
import {test} from 'node:test';
import {Client} from '@modelcontextprotocol/client';
import {InMemoryTransport} from '@modelcontextprotocol/server';
import {createServer} from '../server.mjs';
import {loadConfig} from '../config.mjs';

test('full party availability preserves authoritative slots and rejects private or malformed input', async()=>{
  const id='30000000-0000-4000-8000-000000000011';
  const args={city:'KYOTO',storeId:id,from:'2026-11-10',to:'2026-11-11',guests:[{guestType:'ADULT_FEMALE',planId:id,kimonoId:id}]};
  let seen, calls=0, mode='ok';
  const upstream=httpServer(async(req,res)=>{
    calls++;assert.equal(req.url,'/api/catalog/party-availability');assert.equal(req.headers.authorization,undefined);
    let raw='';for await(const chunk of req)raw+=chunk;seen=JSON.parse(raw);
    res.setHeader('Content-Type','application/json');
    if(mode==='error'){res.writeHead(409);res.end(JSON.stringify({error:{code:'STORE_UNAVAILABLE',message:'門市尚未開放'}}));return;}
    res.end(JSON.stringify({view:'partyAvailability',...seen,store:{id,name:{'zh-Hant':'測試門市'}},
      slots:[{slotId:id,startsAt:'2026-11-10T09:00:00+09:00',endsAt:'2026-11-10T09:30:00+09:00',remaining:2,available:true,reason:null,inventoryChecked:true,isDemo:true,rentalEndsAt:['2026-11-10T17:00:00+09:00']}],
      timezone:'Asia/Tokyo',serverTime:'2026-10-25T10:00:00Z',availabilityChecked:true,inventoryReserved:mode==='invalid',bookingCreated:false,isDemo:true,notice:'未保留庫存、未建立預約。'}));
  }).listen(0,'127.0.0.1');await once(upstream,'listening');
  const server=createServer(loadConfig({KINUTABI_API_BASE_URL:`http://127.0.0.1:${upstream.address().port}`}));
  const client=new Client({name:'availability-test',version:'1'});
  const [a,b]=InMemoryTransport.createLinkedPair();await server.connect(b);await client.connect(a);
  const call=arguments_=>client.callTool({name:'check_party_availability',arguments:arguments_});
  try{
    const result=await call(args);assert.ok(!result.isError,result.content[0].text);assert.deepEqual(seen,args);
    assert.equal(result.structuredContent.slots[0].inventoryChecked,true);assert.equal(result.structuredContent.store.name,'測試門市');
    assert.match(result.content[0].text,/示範資料/);assert.match(result.content[0].text,/未保留/);
    for(const invalid of [{...args,userId:id},{...args,from:'2026-02-30'},{...args,guests:[]}])assert.equal((await call(invalid)).isError,true);
    assert.equal(calls,1);
    mode='error';assert.equal((await call(args)).structuredContent.error.code,'STORE_UNAVAILABLE');
    mode='invalid';assert.equal((await call(args)).structuredContent.error.code,'INVALID_CATALOG_RESPONSE');
  }finally{await client.close();await server.close();await new Promise(resolve=>upstream.close(resolve));}
});
