import type { Draft, Plan } from './domain'

export type Guest={guestType:'ADULT_FEMALE'|'ADULT_MALE';planId:string;kimonoId:string;accessoryIds:string[];generationId?:string}
export type Hold={holdId:string;status:string;expiresAt:string;serverTime:string;total:number}
export type ServerDraft={draftId:string;version:number;data:{storeId:string|null;slotId:string|null;guests:Guest[];contactName:string;contactEmail:string;contactPhone:string};slot?:{startsAt:string}|null;activeHold:Hold|null}
export function toServerDraft(draft:Draft){
 return {storeId:draft.storeId||null,slotId:draft.slot||null,partySize:draft.participants.length,
 guests:draft.participants.map(p=>({guestType:'ADULT_'+p.role,planId:draft.planId,kimonoId:p.kimonoId||null,accessoryIds:p.role==='FEMALE'&&p.beltId?[p.beltId]:[],...(p.generationId?{generationId:p.generationId}:{})})),
 contactName:draft.name,contactEmail:draft.email,contactPhone:draft.phone,locale:'zh-Hant'}
}
export function fromServerDraft(value:ServerDraft,plans:Plan[]):Draft{
 const data=value.data;const planId=data.guests[0]?.planId??'';const plan=plans.find(p=>p.id===planId)
 return {draftId:value.draftId,version:value.version,planId,city:plan?.city??'',storeId:data.storeId??'',slot:data.slotId??'',
 date:value.slot?new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tokyo'}).format(new Date(value.slot.startsAt)):'',
 participants:data.guests.map((g,i)=>({id:'guest_'+i,role:g.guestType==='ADULT_MALE'?'MALE':'FEMALE',kimonoId:g.kimonoId??'',beltId:g.accessoryIds?.[0]??null,generationId:g.generationId})),
 photography:false,name:data.contactName,email:data.contactEmail,phone:data.contactPhone,acceptedPolicy:false}
}
