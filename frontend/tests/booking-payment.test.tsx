import { isValidElement, type ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { BookingPayment } from '../src/components/BookingPayment'
import { PaymentFields } from '../src/components/PaymentFields'
import { request } from '../src/lib/api'

const state=vi.hoisted(()=>({values:[] as unknown[],index:0}))
vi.mock('react',async original=>({...await original<typeof import('react')>(),useEffect:()=>{},
 useState:(initial:unknown)=>{const i=state.index++;if(!(i in state.values))state.values[i]=initial;return[state.values[i],(v:unknown)=>{state.values[i]=typeof v==='function'?v(state.values[i]):v}]},
 useRef:(initial:unknown)=>({current:initial}),
}))
vi.mock('../src/lib/auth',()=>({useAuth:()=>({user:{uid:'member'},token:async()=>'token'})}))
vi.mock('../src/lib/hooks',()=>({useBackend:()=>({capabilities:{payment:true}})}))
vi.mock('../src/lib/api',async original=>({...await original<typeof import('../src/lib/api')>(),request:vi.fn()}))

function find(node:ReactNode,type:unknown):Record<string,unknown>|undefined{
 if(Array.isArray(node))return node.map(n=>find(n,type)).find(Boolean)
 if(!isValidElement<{children?:ReactNode}>(node))return
 if(node.type===type)return node.props as Record<string,unknown>
 return find(node.props.children,type)
}
const props={hold:{holdId:'hold',quoteToken:'quote',status:'HELD',total:1500,expiresAt:'2099-01-01',serverTime:'2026-11-07'},remaining:500,contact:{name:'旅客',email:'test@example.com',phone:'0900000000'},onRelease:vi.fn()}
beforeEach(()=>{state.values=[true,true,false,null,'',false];state.index=0;vi.mocked(request).mockReset()})

it('重複提交只送出一次付款，使用暫留報價與政策版本且不信任前端金額',async()=>{
 let resolve!:(v:unknown)=>void
 vi.mocked(request).mockImplementation(()=>new Promise(r=>{resolve=r}) as never)
 const tree=BookingPayment(props);const fields=find(tree,PaymentFields)!
 const pay=fields.onPrime as (prime:string)=>Promise<void>
 const first=pay('ephemeral-prime');await Promise.resolve();await pay('second-prime')
 expect(request).toHaveBeenCalledTimes(1)
 const call=vi.mocked(request).mock.calls[0]
 expect(call[0]).toBe('/api/bookings')
 expect(call[1]?.body).toEqual({holdId:'hold',quoteToken:'quote',prime:'ephemeral-prime',acceptedPolicy:true,policyVersion:'cancellation-7days-v1'})
 resolve({orderNo:'order',paymentStatus:'PAYMENT_PENDING'});await first
 expect(state.values[3]).toEqual({orderNo:'order',paymentStatus:'PAYMENT_PENDING'})
})

it('付款回應遺失後停用信用卡提交，先查回原單',async()=>{
 vi.mocked(request).mockRejectedValueOnce(new Error('連線中斷'))
 const fields=find(BookingPayment(props),PaymentFields)!
 await (fields.onPrime as (p:string)=>Promise<void>)('ephemeral-prime')
 state.index=0
 expect(find(BookingPayment(props),PaymentFields)).toBeUndefined()
 expect(state.values[4]).toBe('連線中斷')
})

it('未同意政策或暫留到期不送付款',async()=>{
 state.values[0]=false
 const fields=find(BookingPayment(props),PaymentFields)!
 expect(fields.disabled).toBe(true)
 await (fields.onPrime as (p:string)=>Promise<void>)('prime')
 expect(request).not.toHaveBeenCalled()
 state.index=0
 expect(find(BookingPayment({...props,remaining:0}),PaymentFields)).toBeUndefined()
})
