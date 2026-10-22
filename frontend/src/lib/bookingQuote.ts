export type Quote = {
  quoteToken: string
  currency: string
  total: number
  expiresAt: string
  lineItems?: { label: string; amount: number }[]
}

export function quoteExpired(quote: Quote, now = Date.now()) {
  const expiry = Date.parse(quote.expiresAt)
  return !Number.isFinite(expiry) || expiry <= now
}

export function validateQuote(quote: Quote, now = Date.now()) {
  if (quote.currency !== 'TWD' || !Number.isSafeInteger(quote.total) || quote.total < 0)
    throw new Error('正式報價須為 TWD 整數元，請重新取得報價。')
  if (!quote.quoteToken?.trim() || !Number.isFinite(Date.parse(quote.expiresAt)))
    throw new Error('正式報價資料不完整，請重新取得報價。')
  if (quoteExpired(quote, now)) throw new Error('報價已到期，請重新取得正式報價。')
}
