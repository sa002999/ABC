import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { BookingQuote } from '../src/components/BookingQuote'
import { quoteExpired, validateQuote, type Quote } from '../src/lib/bookingQuote'

const now = Date.parse('2026-10-20T00:00:00Z')
const quote: Quote = {
  quoteToken: 'server-quote', currency: 'TWD', total: 2400,
  expiresAt: '2026-10-20T00:05:00Z',
  lineItems: [{ label: '和服方案', amount: 2400 }],
}
const base = { quote: null, expired: false, failed: false, busy: false, disabled: false, onAction() {} }

describe('正式報價的有效期限與金額', () => {
  it('到期當下與無效期限皆不能進入付款', () => {
    expect(quoteExpired(quote, now)).toBe(false)
    expect(quoteExpired(quote, Date.parse(quote.expiresAt))).toBe(true)
    expect(quoteExpired({ ...quote, expiresAt: 'invalid' }, now)).toBe(true)
    expect(() => validateQuote(quote, Date.parse(quote.expiresAt))).toThrow('報價已到期')
  })
  it('只接受有識別碼且有效的 TWD 整數正式報價', () => {
    expect(() => validateQuote(quote, now)).not.toThrow()
    for (const patch of [{ currency: 'JPY' }, { total: 1.5 }, { total: -1 }, { quoteToken: '' }, { expiresAt: 'invalid' }])
      expect(() => validateQuote({ ...quote, ...patch }, now)).toThrow()
  })
})

describe('單一報價按鈕', () => {
  it('未報價、取得中與失敗時不提供付款入口', () => {
    const initial = renderToStaticMarkup(<BookingQuote {...base} />)
    expect(initial).toContain('尚未取得正式報價')
    expect(initial.match(/<button /g)).toHaveLength(1)
    const fetching = renderToStaticMarkup(<BookingQuote {...base} busy />)
    expect(fetching).toContain('取得報價中…')
    expect(fetching).toContain('disabled=""')
    const failed = renderToStaticMarkup(<BookingQuote {...base} failed />)
    expect(failed).toContain('重新取得正式報價')
    expect(failed).not.toContain('確認報價並前往付款')
  })
  it('正式總價與明細在付款按鈕上方，到期後移除付款入口與舊價格', () => {
    const ready = renderToStaticMarkup(<BookingQuote {...base} quote={quote} />)
    expect(ready).toContain('和服方案')
    expect(ready).toContain('台幣 TWD')
    expect(ready.indexOf('正式總價')).toBeLessThan(ready.indexOf('<button '))
    expect(ready).toContain('確認報價並前往付款')
    expect(ready.match(/<button /g)).toHaveLength(1)
    const expired = renderToStaticMarkup(<BookingQuote {...base} quote={quote} expired />)
    expect(expired).toContain('報價已到期')
    expect(expired).toContain('重新取得正式報價')
    expect(expired).not.toContain('確認報價並前往付款')
    expect(expired).not.toContain('2,400')
  })
})
