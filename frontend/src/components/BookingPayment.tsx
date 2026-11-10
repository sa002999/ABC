import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { PaymentFields } from './PaymentFields'
import { Button, ButtonLink, Check, Container, Loading, Notice, PageHeading, Panel } from './ui'
import { actionKey, localized, request } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useBackend } from '../lib/hooks'
import type { Hold } from '../lib/bookingApi'
import { money, paymentLabel, type Order } from '../lib/domain'

function OrderResult({order}:{order:Order}){
 return <div className="space-y-5"><p className="break-all">訂單編號：{order.orderNo}</p><p>{paymentLabel(order.paymentStatus)}</p>{order.bookingNo?<ButtonLink primary to={'/booking/complete/'+encodeURIComponent(order.bookingNo)}>查看預約成功資訊</ButtonLink>:order.paymentStatus==='FAILED'?<><Notice>付款未成功，資源已釋放。請重新報價及暫留後再付款。</Notice><ButtonLink to="/booking">返回預約</ButtonLink></>:<><Notice>{['REVIEW_REQUIRED','REFUND_REQUIRED'].includes(order.paymentStatus)?'交易需人工查核，請保留訂單編號，勿重複付款。':'付款結果確認中。即使暫留倒數結束，也不會釋放這筆待確認交易的資源。請勿重複付款。'}</Notice><ButtonLink to={'/booking/payment/'+encodeURIComponent(order.orderNo)}>查看訂單處理狀態</ButtonLink></>}</div>
}

export function BookingPayment({hold,remaining,onRelease,contact}:{hold:Hold;remaining:number;onRelease:()=>void;contact:{name:string;email:string;phone:string}}){
 const auth=useAuth();const backend=useBackend();const[accepted,setAccepted]=useState(false);const[ready,setReady]=useState(false);const[attempted,setAttempted]=useState(false);const[order,setOrder]=useState<Order|null>(null);const[error,setError]=useState('');const[checking,setChecking]=useState(false)
 const key=useRef(actionKey());const submitting=useRef(false);const recovering=useRef(false)
 async function recover(){if(recovering.current||submitting.current)return;recovering.current=true;setChecking(true);setError('');try{
  const fresh=await request<Hold>('/api/availability/holds/'+hold.holdId,{token:await auth.token()})
  if(fresh.orderNo){const value=await request<Order>('/api/orders/'+fresh.orderNo,{token:await auth.token()});setOrder(value);setAttempted(true)}
  else {setReady(fresh.status==='HELD');setAttempted(false)}
 }catch(e){setError((e as Error).message)}finally{recovering.current=false;setChecking(false)}}
 useEffect(()=>{void recover()},[hold.holdId])
 useEffect(()=>{if(!order||order.paymentStatus!=='PAYMENT_PENDING')return;const timer=setInterval(()=>void recover(),5000);return()=>clearInterval(timer)},[order?.orderNo,order?.paymentStatus])
 async function pay(prime:string){
  if(submitting.current||!accepted||remaining<=0)return
  submitting.current=true;setAttempted(true);setError('')
  try{setOrder(await request<Order>('/api/bookings',{method:'POST',token:await auth.token(),key:key.current,
    body:{holdId:hold.holdId,quoteToken:hold.quoteToken,prime,acceptedPolicy:true,policyVersion:'cancellation-7days-v1'}}))}
  catch(e){setError((e as Error).message)}finally{submitting.current=false}
 }
 return <Panel><h2 className="font-serif text-2xl">Sandbox 信用卡付款</h2><p className="my-4">{money(hold.total)} · {order?'交易狀態以查核結果為準':`暫留剩餘 ${Math.floor(remaining/60)} 分 ${remaining%60} 秒`}</p>
 {hold.snapshot&&<div className="my-5 space-y-3 text-sm"><p>{localized(hold.snapshot.storeName)} · {new Date(hold.snapshot.startsAt).toLocaleString('zh-TW',{timeZone:'Asia/Tokyo'})}（日本時間）</p>{hold.snapshot.lineItems.map((line,i)=><p key={i}>{localized(line.name)} · {money(line.total)}</p>)}</div>}<p className="my-4 text-sm break-words">{contact.name} · {contact.email} · {contact.phone}</p>
 {error&&<Notice tone="error">{error}</Notice>}
 {order?<OrderResult order={order}/>:attempted?<Notice>已嘗試提交付款，請先查回原訂單，勿再次提交。</Notice>:!ready?<Notice>{checking?'正在恢復原暫留與訂單…':'暫留已失效或需重新查詢。'}</Notice>:remaining<=0?<Notice>暫留已到期，請返回草稿重新報價。</Notice>:<>
 <p className="my-4 text-sm leading-7">依日本當地預約開始時間計算，超過 7×24 小時取消全額退款；等於或少於 7×24 小時不退款。改期須取消原預約並重新預約。<a href="/cancellation" target="_blank" rel="noreferrer" className="underline">查看完整取消政策</a></p>
 <Check checked={accepted} onChange={e=>setAccepted(e.target.checked)}>我已確認預約金額與聯絡資料，並同意取消政策。</Check>
 {backend.capabilities.payment?<div className="mt-6"><PaymentFields disabled={!accepted||remaining<=0} onPrime={pay}/></div>:<Notice>Sandbox 金流暫時無法使用，請確認後端設定。</Notice>}
 </>}
 <div className="mt-6 flex flex-wrap gap-3"><Button disabled={checking||submitting.current} onClick={()=>void recover()}>查詢原訂單／暫留</Button>{!order&&!attempted&&<Button disabled={checking} onClick={onRelease}>釋放暫留並返回草稿</Button>}</div></Panel>
}

export function PaymentStatus(){
 const{orderNo}=useParams();const auth=useAuth();const backend=useBackend();const[order,setOrder]=useState<Order|null>(null);const[error,setError]=useState('');const[version,setVersion]=useState(0)
 useEffect(()=>{setOrder(null);setError('');if(!auth.user||!backend.capabilities.orderRead)return;let active=true;let timer:ReturnType<typeof setTimeout>
  async function load(){try{const value=await request<Order>('/api/orders/'+encodeURIComponent(orderNo??''),{token:await auth.token()});if(!active)return;setOrder(value);setError('');if(value.paymentStatus==='PAYMENT_PENDING')timer=setTimeout(load,5000)}catch(e){if(active)setError((e as Error).message)}}
  void load();return()=>{active=false;clearTimeout(timer)}
 },[auth.user?.uid,orderNo,version,backend.capabilities.orderRead])
 return <Container><PageHeading eyebrow="PAYMENT STATUS" title="付款處理狀態"/>{!auth.user?<ButtonLink to={'/login?returnTo='+encodeURIComponent('/booking/payment/'+orderNo)}>登入後查詢本人訂單</ButtonLink>:<Panel>{error&&<Notice tone="error">{error}</Notice>}{order?<OrderResult order={order}/>:!error&&<Loading/>}<Button className="mt-6" onClick={()=>setVersion(v=>v+1)}>重新查詢</Button></Panel>}<div className="mt-6"><ButtonLink to="/bookings">我的預約</ButtonLink></div></Container>
}
