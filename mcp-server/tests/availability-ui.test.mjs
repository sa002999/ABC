import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {test} from 'node:test';

const script=(await readFile(new URL('../ui/plan-picker.mjs',import.meta.url),'utf8')).replace(/^import .*?;\r?\n/gm,'');
test('date UI restores the party, selects only available slots and invalidates old results on changes',async()=>{
  class Element{
    constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.listeners={};this.style={};this.textContent='';}
    append(...children){this.children.push(...children);}
    replaceChildren(...children){this.children=children;}
    addEventListener(name,fn){this.listeners[name]=fn;}
  }
  const ids=Object.fromEntries(['status','search','previous','next','selection','outfits','notice','city','party-size','keyword','sort','page','plans','filters'].map(id=>[id,new Element('div')]));
  const all=()=>Object.values(ids).flatMap(function walk(node){return [node,...node.children.flatMap(walk)];});
  const calls=[],contexts=[],opened=[];let sdk;
  const paymentUrl='https://example.test/booking?draftId=draft&holdId=hold';
  const guest={planId:'plan',kimonoId:'kimono',guestType:'ADULT_FEMALE'};
  const slot={slotId:'slot',startsAt:'2026-11-10T00:00:00Z',rentalEndsAt:['2026-11-10T08:00:00Z'],available:true};
  const data={view:'partyAvailability',city:'KYOTO',guests:[guest],storeId:'store',from:'2026-11-10',to:'2026-11-11',serverTime:'2026-10-25T10:00:00Z',slots:[slot,{...slot,slotId:'full',available:false,reason:'SLOT_FULL'}],isDemo:true,notice:'未保留'};
  class App{
    constructor(){sdk=this;}async connect(){}async updateModelContext(value){contexts.push(JSON.parse(value.content[0].text.split('：')[1].split('。此為')[0]));}
    getHostCapabilities(){return {openLinks:true};}
    async openLink({url}){opened.push(url);}
    async callServerTool(call){
      calls.push(call);
      if(call.name==='get_plan_details')return {structuredContent:{view:'plan',plan:{id:'plan',name:'方案'}}};
      if(call.name==='check_outfit_summary')return {structuredContent:{view:'outfitSummary',estimatedTotal:1500,lineItems:[],commonStores:[{id:'store',name:'門市'}]}};
      if(call.name==='list_kimonos')return {structuredContent:{view:'kimonos',kimonos:[{id:'kimono',name:'和服',sku:'sku',gender:'FEMALE',styleTags:[]}],nextPage:null}};
      if(call.name==='prepare_booking')return {structuredContent:{view:'bookingQuote',draftId:'draft',quoteToken:'quote',
        storeName:'門市',startsAt:slot.startsAt,total:1500,lineItems:[{name:'和服',total:1500}],paymentAvailable:true}};
      if(call.name==='confirm_booking_hold')return {structuredContent:{view:'bookingHold',paymentUrl,expiresAt:'2026-11-10T00:10:00Z'}};
      assert.equal(call.name,'check_party_availability');return {structuredContent:{...data,...call.arguments,slots:[]}};
    }
  }
  const context=vm.createContext({App,Date,Intl,URL,crypto:{randomUUID:()=> 'conversation'},window:{parent:{}},document:{getElementById:id=>ids[id],createElement:tag=>new Element(tag),querySelectorAll:()=>all().filter(node=>node.dataset.action)}});
  vm.runInContext(script,context);
  const flush=async()=>{for(let i=0;i<100;i++)await Promise.resolve();};await flush();
  await sdk.ontoolresult({structuredContent:data});await flush();
  const action=name=>all().filter(node=>node.dataset.action===name);
  assert.equal(action('availability-slot').length,1,ids.status.textContent);
  assert.equal(contexts.at(-1).availabilityChecked,true);
  await action('availability-slot')[0].listeners.click();await flush();
  assert.equal(contexts.at(-1).selectedSlot.slotId,'slot');assert.equal(contexts.at(-1).inventoryReserved,false);
  assert.equal(calls.some(call=>call.name==='prepare_booking'),false);
  await action('booking-quote')[0].listeners.click();await flush();
  assert.equal(calls.at(-1).name,'prepare_booking');
  assert.equal(calls.at(-1).arguments.slotId,'slot');
  assert.equal(calls.some(call=>call.name==='confirm_booking_hold'),false);
  await action('booking-confirm')[0].listeners.click();await flush();
  assert.equal(calls.at(-1).arguments.quoteToken,'quote');
  assert.equal(calls.at(-1).arguments.confirmed,true);
  assert.deepEqual(opened,[paymentUrl]);
  assert.equal(contexts.at(-1).inventoryReserved,true);
  const date=action('availability-from')[0];date.value='2026-11-11';await date.listeners.change();await flush();
  assert.equal(contexts.at(-1).availabilityChecked,false);assert.equal(contexts.at(-1).selectedSlot,null);
  assert.equal(contexts.at(-1).guests[0].kimonoId,'kimono');assert.equal(action('availability-slot').length,0);
  await action('availability-query')[0].listeners.click();await flush();
  assert.equal(calls.at(-1).arguments.from,'2026-11-11');assert.equal(calls.at(-1).arguments.guests[0].kimonoId,'kimono');
  assert.equal(action('availability-slot').length,0);assert.ok(all().some(node=>node.textContent.includes('搭配已保留')));
  await action('garment')[0].listeners.click();await flush();
  assert.equal(contexts.at(-1).availabilityChecked,false);assert.equal(contexts.at(-1).availabilityFilters,null);
  assert.ok(calls.every(call=>['get_plan_details','check_outfit_summary','list_kimonos','check_party_availability','prepare_booking','confirm_booking_hold'].includes(call.name)));
});
