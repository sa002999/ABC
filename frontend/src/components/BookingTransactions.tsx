import { money, paymentLabel } from '../lib/domain'

export type RefundSummary={id:string;amount:number;currency:string;status:string;isCaptured?:boolean|null}
export type TransactionSummary={total?:number;paymentStatus?:string;refunds?:RefundSummary[];cancellations?:{kind:string;reason:string;amount:number}[];notifications?:{kind:string;status:string}[]}
export const bookingStatus=(value?:string)=>({CONFIRMED:'預約成立',CHECKED_IN:'已報到',REDEEMED:'已核銷',RENTED:'出借中',RETURNED:'已歸還、待整備',COMPLETED:'已完成',CANCELLED:'已取消',NO_SHOW:'未到場'}[value??'']??value??'')
export const refundStatus=(value:string)=>({REQUESTED:'待授權人員處理',PROCESSING:'已送出、銀行查核中',SUCCEEDED:'已完成',FAILED:'未成功，待人員處理',REVIEW_REQUIRED:'結果待查核，請勿重複退款'}[value]??value)

export function BookingTransactions({value}: {value:TransactionSummary}){
 return <div className="mt-6 space-y-3 border-t border-line pt-5 text-sm leading-7">
  {value.total!==undefined&&<p>訂單總額：{money(value.total)}</p>}
  {value.paymentStatus&&<p>付款狀態：{paymentLabel(value.paymentStatus)}</p>}
  {value.refunds?.map(r=><div key={r.id}><p>退款金額：{money(r.amount)} · {refundStatus(r.status)}</p><p className="break-all text-xs text-muted">退款編號：{r.id}</p></div>)}
  {value.cancellations?.map((c,i)=><p key={i}>{c.kind==='WEATHER'?'攝影取消':c.kind==='MERCHANT'?'商家取消':'會員取消'}：{c.reason}{c.amount===0?'（依政策不退款）':''}</p>)}
  {!!value.notifications?.length&&<p className="text-xs text-muted">通知 Email：{value.notifications.every(n=>n.status==='SENT')?'已寄出':value.notifications.some(n=>n.status==='REVIEW_REQUIRED')?'寄送結果待查核':'尚未寄出／等待寄信服務設定'}</p>}
 </div>
}
