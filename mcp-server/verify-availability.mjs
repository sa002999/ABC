import assert from 'node:assert/strict';
import {Client,StreamableHTTPClientTransport} from '@modelcontextprotocol/client';

// Read-only smoke test against running local services. No member token or booking mutation.
const client=new Client({name:'kinu-tabi-live-availability',version:'1'});
try{
  await client.connect(new StreamableHTTPClientTransport(new URL('http://127.0.0.1:3001/mcp')));
  const call=async(name,args)=>{
    const result=await client.callTool({name,arguments:args});
    assert.ok(!result.isError,result.content?.[0]?.text);return result.structuredContent;
  };
  const list=await call('list_plans',{city:'KYOTO',partySize:3});
  const plan=list.plans.find(p=>p.kind==='GROUP');assert.ok(plan,'Need a group plan in the test catalogue');
  const garments=await call('list_kimonos',{city:'KYOTO',planId:plan.id});
  const garment=garments.kimonos.find(k=>k.gender==='FEMALE');assert.ok(garment);
  const guests=Array.from({length:3},()=>({guestType:'ADULT_FEMALE',planId:plan.id,kimonoId:garment.id}));
  const summary=await call('check_outfit_summary',{city:'KYOTO',guests});
  const store=summary.commonStores.find(s=>/示範|測試|demo/i.test(s.name)) || summary.commonStores[0];assert.ok(store);
  const date=offset=>new Date(Date.now()+offset*86400000).toISOString().slice(0,10);
  const args={city:'KYOTO',guests,storeId:store.id,from:date(30),to:date(60)};
  const start=performance.now();const data=await call('show_party_availability',args);
  assert.equal(data.timezone,'Asia/Tokyo');assert.equal(data.inventoryReserved,false);assert.equal(data.bookingCreated,false);
  assert.ok(data.slots.length);assert.ok(data.slots.filter(s=>s.available).every(s=>s.inventoryChecked && s.rentalEndsAt.length===3));
  const tools=await client.listTools();const uri=tools.tools.find(t=>t.name==='show_party_availability')._meta.ui.resourceUri;
  const resource=await client.readResource({uri});assert.ok(resource.contents[0].text.includes('查全員日期與時段'));
  console.log(JSON.stringify({liveAvailability:true,guests:3,days:31,slots:data.slots.length,available:data.slots.filter(s=>s.available).length,isDemo:data.isDemo,elapsedSeconds:Math.round((performance.now()-start)/100)/10,resource:uri,nativeHostVerified:false}));
}finally{await client.close();}
