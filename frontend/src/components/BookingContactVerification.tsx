import { useEffect, useId, useRef, useState } from 'react'
import { RecaptchaVerifier, signInWithPhoneNumber, signOut, type ConfirmationResult } from 'firebase/auth'
import { phoneVerificationAuth } from '../lib/auth'
import { normalizeMobile, phoneError } from '../lib/memberProfile'
import { Button, Field, Notice, inputClass } from './ui'

function VerificationStatus({verified}:{verified:boolean}){
 return <span role="status" className={`px-2 py-1 text-xs ${verified?'bg-forest/10 text-forest':'bg-wash text-muted'}`}>
  {verified?'已驗證':'尚未驗證'}
 </span>
}

const fieldRow='grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]'
const sendButton='border-forest px-4 text-forest hover:bg-forest'

export function BookingContactVerification({email, emailVerified, phoneVerified, phone, editable, onEmailChange, onPhoneChange, onPhoneBlur, normalizePhone, submit}: {
 email:string; emailVerified:boolean; phoneVerified:boolean; phone:string; editable:boolean
 onEmailChange:(email:string)=>void
 onPhoneChange:(phone:string)=>void
 onPhoneBlur:()=>void
 normalizePhone:(phone:string)=>void
 submit:(path:string, body?:object)=>Promise<boolean>
}){
 const emailId=useId();const phoneId=useId()
 const [emailSent,setEmailSent]=useState(false)
 const [emailCode,setEmailCode]=useState('')
 const [smsCode,setSmsCode]=useState('')
 const [smsBusy,setSmsBusy]=useState(false)
 const [smsError,setSmsError]=useState('')
 const [sentPhone,setSentPhone]=useState('')
 const host=useRef<HTMLDivElement>(null)
 const captcha=useRef<RecaptchaVerifier|null>(null)
 const confirmation=useRef<ConfirmationResult|null>(null)

 useEffect(()=>()=>captcha.current?.clear(),[])

 async function sendSms(){
  setSmsBusy(true);setSmsError('')
  try{
   const value=phone.replace(/[\s()-]/g,'')
   const country=value.startsWith('+81')?'+81':'+886'
   const normalized=normalizeMobile(country,value)
   normalizePhone(normalized)
   const secondary=phoneVerificationAuth()
   secondary.languageCode='zh-TW'
   await signOut(secondary)
   if(!host.current)return
   captcha.current?.clear()
   captcha.current=new RecaptchaVerifier(secondary,host.current,{size:'normal'})
   confirmation.current=await signInWithPhoneNumber(secondary,normalized,captcha.current)
   setSentPhone(normalized);setSmsCode('')
  }catch(error){
   captcha.current?.clear();captcha.current=null
   setSmsError(phoneError(error))
  }finally{setSmsBusy(false)}
 }

 async function confirmSms(){
  if(!confirmation.current||phone!==sentPhone)return
  setSmsBusy(true);setSmsError('')
  try{
   const result=await confirmation.current.confirm(smsCode)
   try{await submit('phone',{phoneToken:await result.user.getIdToken(true)})}
   finally{await signOut(phoneVerificationAuth())}
  }catch(error){setSmsError(phoneError(error))}
  finally{setSmsBusy(false)}
 }

 return <>
  <div className="space-y-3">
   <div className="flex items-center justify-between gap-3">
    <label htmlFor={emailId} className="text-sm">Email</label>
    <VerificationStatus verified={emailVerified}/>
   </div>
   <div className={editable&&!emailVerified?fieldRow:undefined}>
    <input id={emailId} required type="email" autoComplete="email" maxLength={40} value={email} readOnly={!editable}
     onChange={event=>{onEmailChange(event.target.value);setEmailSent(false);setEmailCode('')}} className={inputClass}/>
    {editable&&!emailVerified&&<Button className={sendButton} aria-label={emailSent?'重新寄送 Email 驗證碼':'傳送 Email 驗證碼'} onClick={async()=>{if(await submit('email'))setEmailSent(true)}}>
     {emailSent?'重新寄送驗證碼':'傳送驗證碼'}
    </Button>}
   </div>
   {editable&&!emailVerified&&<details open={emailSent}>
    <summary className="cursor-pointer text-xs text-muted">已有 Email 驗證碼</summary>
    <div className={fieldRow+' sm:items-end'}>
    <Field label="Email 驗證碼"><input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={emailCode} onChange={event=>setEmailCode(event.target.value)} className={inputClass}/></Field>
    <Button className={sendButton} disabled={!/^\d{6}$/.test(emailCode)} onClick={()=>void submit('email/confirm',{code:emailCode})}>驗證聯絡 Email</Button>
    </div>
   </details>}
  </div>
  <div className="space-y-3">
   <div className="flex items-center justify-between gap-3">
    <label htmlFor={phoneId} className="text-sm">手機號碼</label>
    <VerificationStatus verified={phoneVerified}/>
   </div>
   <div className={editable&&!phoneVerified?fieldRow:undefined}>
    <input id={phoneId} required type="tel" autoComplete="tel" maxLength={30} placeholder="0912345678 或 +819012345678" value={phone}
     readOnly={!editable} onBlur={onPhoneBlur} onChange={event=>onPhoneChange(event.target.value)} className={inputClass}/>
    {editable&&!phoneVerified&&<Button className={sendButton} aria-label={sentPhone===phone?'重新傳送簡訊驗證碼':'傳送簡訊驗證碼'} disabled={smsBusy||!phone.trim()} onClick={()=>void sendSms()}>
     {sentPhone===phone?'重新傳送驗證碼':'傳送驗證碼'}
    </Button>}
   </div>
   {editable&&!phoneVerified&&<>
    <p className="text-xs leading-6 text-muted">支援台灣與日本手機。發送簡訊時，Google 會處理手機號碼以完成驗證。</p>
    <div ref={host}/>
    {sentPhone===phone&&sentPhone&&<div className={fieldRow+' sm:items-end'}>
     <Field label="簡訊驗證碼"><input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={smsCode} onChange={event=>setSmsCode(event.target.value)} className={inputClass}/></Field>
     <Button className={sendButton} disabled={smsBusy||!/^\d{6}$/.test(smsCode)} onClick={()=>void confirmSms()}>驗證聯絡手機</Button>
    </div>}
    {smsError&&<Notice tone="error">{smsError}</Notice>}
   </>}
  </div>
 </>
}
