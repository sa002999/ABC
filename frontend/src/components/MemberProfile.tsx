import { useEffect, useRef, useState } from 'react'
import { RecaptchaVerifier, signInWithPhoneNumber, signOut, type ConfirmationResult } from 'firebase/auth'
import { Button, Field, Loading, Notice, Panel, Select, inputClass } from './ui'
import { request } from '../lib/api'
import { phoneVerificationAuth, reauthenticateMember, useAuth } from '../lib/auth'
import { usePrivateResource } from '../lib/hooks'
import { normalizeMobile, phoneError, type MemberProfile as Profile } from '../lib/memberProfile'

export function MemberProfile({onSaved}:{onSaved?:(profile:Profile)=>void}={}){
 const auth=useAuth();const profile=usePrivateResource<Profile|null>('/api/account',null)
 const[name,setName]=useState('');const[country,setCountry]=useState('+886');const[mobile,setMobile]=useState('');const[password,setPassword]=useState('');const[code,setCode]=useState('')
 const[busy,setBusy]=useState(false);const[message,setMessage]=useState('');const[sentTo,setSentTo]=useState('');const[cooldown,setCooldown]=useState(0)
 const captchaHost=useRef<HTMLDivElement>(null);const captcha=useRef<RecaptchaVerifier|null>(null);const confirmation=useRef<ConfirmationResult|null>(null)
 const alive=useRef(true);const operation=useRef(false)
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;captcha.current?.clear();confirmation.current=null}},[])
 useEffect(()=>{setName(profile.data?.displayName??'')},[profile.data?.displayName])
 useEffect(()=>{if(!cooldown)return;const timer=setTimeout(()=>setCooldown(value=>Math.max(0,value-1)),1000);return()=>clearTimeout(timer)},[cooldown])
 async function perform(action:()=>Promise<void>){
  if(operation.current)return
  operation.current=true;setBusy(true);setMessage('')
  try{await action()}catch(error){if(alive.current)setMessage(phoneError(error))}
  finally{operation.current=false;if(alive.current)setBusy(false)}
 }
 function resetPhone(){confirmation.current=null;setSentTo('');setCode('');captcha.current?.clear();captcha.current=null}
 async function saveName(){await perform(async()=>{
  const token=await auth.token()
  if(!alive.current)return
  const saved=await request<Profile>('/api/account',{method:'PATCH',token,body:{displayName:name.trim()}})
  if(alive.current){profile.setData(saved);onSaved?.(saved);setMessage('會員姓名已保存。')}
 })}
 async function sendCode(){if(cooldown>0)return;await perform(async()=>{
  const phone=normalizeMobile(country,mobile)
  const uid=auth.user!.uid
  await reauthenticateMember(password,uid)
  if(!alive.current)return
  resetPhone()
  const secondary=phoneVerificationAuth();secondary.languageCode='zh-TW'
  await signOut(secondary)
  if(!alive.current)return
  captcha.current=new RecaptchaVerifier(secondary,captchaHost.current!,{size:'normal'})
  try{
   const result=await signInWithPhoneNumber(secondary,phone,captcha.current)
   if(alive.current){confirmation.current=result;setSentTo(phone);setCooldown(60);setMessage('驗證碼已寄出，請查看手機簡訊。')}
  }catch(error){captcha.current?.clear();captcha.current=null;throw error}
 })}
 async function confirmCode(){await perform(async()=>{
  if(!confirmation.current)throw new Error('請先發送驗證碼。')
  const token=await reauthenticateMember(password,auth.user!.uid)
  if(!alive.current)return
  const result=await confirmation.current.confirm(code)
  try{
   const phoneToken=await result.user.getIdToken(true)
   if(!alive.current)return
   const saved=await request<Profile>('/api/account/phone',{method:'POST',token,body:{phoneToken}})
   if(alive.current){profile.setData(saved);onSaved?.(saved);resetPhone();setMobile('');setPassword('');setMessage('手機已完成驗證並綁定。')}
  }finally{await signOut(phoneVerificationAuth())}
 })}
 if(profile.loading)return <Loading/>
 if(profile.error)return <Notice tone="error">{profile.error}<Button onClick={profile.reload}>重試</Button></Notice>
 if(!profile.data)return null
 return <Panel><h2 className="font-serif text-2xl">會員資料</h2>
  <form className="mt-6 space-y-5" onSubmit={event=>{event.preventDefault();void saveName()}}>
   <Field label="會員姓名"><input required maxLength={100} autoComplete="name" value={name} onChange={event=>setName(event.target.value)} className={inputClass} disabled={busy}/></Field>
   <Button type="submit" disabled={busy||!name.trim()}>保存姓名</Button>
  </form>
  <div className="my-8 space-y-4 border-y border-line py-6">
   <Field label="Email"><input type="email" value={profile.data.email} readOnly autoComplete="email" className={inputClass}/></Field>
   <p className="text-sm">{profile.data.emailVerified?'Email 已驗證':'Email 尚未驗證'} · Email 為登入帳號，目前不提供修改。</p>
   {!profile.data.emailVerified&&<div className="flex flex-wrap gap-3">
    <Button disabled={busy} onClick={()=>void perform(async()=>{await auth.verify();if(alive.current)setMessage('驗證信已寄出，請查看信箱。')})}>重寄驗證信</Button>
    <Button disabled={busy} onClick={()=>void perform(async()=>{await auth.refresh();if(alive.current){profile.reload();setMessage('已更新 Email 驗證狀態。')}})}>我已驗證，刷新狀態</Button>
   </div>}
  </div>
  <h3 className="font-serif text-xl">手機綁定</h3>
  <p className="mt-3 text-sm">{profile.data.phoneVerified?`${profile.data.phoneNumber} · 已驗證`:'尚未綁定手機'}</p>
  <p className="mt-3 text-sm leading-7 text-muted">手機僅供會員綁定，不作為登入方式。更換手機須重新驗證登入密碼及新號碼；成功前保留原綁定。</p>
  <form className="mt-5 space-y-5" onSubmit={event=>{event.preventDefault();void (sentTo?confirmCode():sendCode())}}>
   <fieldset disabled={busy} className="space-y-5">
    <Field label="國碼"><Select value={country} disabled={!!sentTo} onChange={event=>setCountry(event.target.value)}><option value="+886">台灣 +886</option><option value="+81">日本 +81</option></Select></Field>
    <Field label={profile.data.phoneVerified?'新手機號碼':'手機號碼'}><input required type="tel" autoComplete="tel-national" value={mobile} disabled={!!sentTo} onChange={event=>setMobile(event.target.value)} placeholder={country==='+886'?'0912345678':'09012345678'} className={inputClass}/></Field>
    <Field label="目前登入密碼"><input required type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)} className={inputClass}/></Field>
    {sentTo&&<><p className="text-sm">驗證碼已發送至 {sentTo}</p><Field label="簡訊驗證碼"><input required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event=>setCode(event.target.value)} className={inputClass}/></Field></>}
   </fieldset>
   <p className="text-xs leading-6 text-muted">點選發送代表同意由 Google 處理手機號碼以提供驗證及防濫用服務；可能產生電信簡訊費用。</p>
   <div ref={captchaHost}/>
   <div className="flex flex-wrap gap-3">
    <Button type="submit" disabled={busy||(!sentTo&&cooldown>0)}>{sentTo?'確認驗證並綁定':cooldown?`${cooldown} 秒後可重新發送`:'發送驗證碼'}</Button>
    {sentTo&&<><Button disabled={busy||cooldown>0} onClick={()=>void sendCode()}>{cooldown?`${cooldown} 秒後可重寄`:'重新發送'}</Button><Button disabled={busy} onClick={resetPhone}>更改輸入號碼</Button></>}
   </div>
  </form>
  {message&&<div role="status" className="mt-5"><Notice>{message}</Notice></div>}
 </Panel>
}
