import { describe, expect, it } from 'vitest'
import { normalizeMobile } from '../src/lib/memberProfile'

describe('會員手機國碼與格式',()=>{
 it('台灣、日本本地及國際格式都儲存為 E.164',()=>{
  expect(normalizeMobile('+886','0912-345-678')).toBe('+886912345678')
  expect(normalizeMobile('+886','+886 912345678')).toBe('+886912345678')
  expect(normalizeMobile('+81','090-1234-5678')).toBe('+819012345678')
  expect(normalizeMobile('+81','08012345678')).toBe('+818012345678')
 })
 it('拒絕非手機、未支援國家、國碼不符及錯誤長度',()=>{
  for(const [country,phone] of [['+886','0212345678'],['+886','09123'],['+81','+886912345678'],['+1','5551234567'],['+81','0312345678']])
   expect(()=>normalizeMobile(country,phone)).toThrow()
 })
})
