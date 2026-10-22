import { money } from '../lib/domain'
import type { Quote } from '../lib/bookingQuote'

type Props = {
  quote: Quote | null
  expired: boolean
  failed: boolean
  busy: boolean
  disabled: boolean
  onAction: () => void
}

export function BookingQuote({ quote, expired, failed, busy, disabled, onAction }: Props) {
  const ready = !!quote && !expired
  const label = busy
    ? ready ? '正在前往付款…' : '取得報價中…'
    : ready ? '確認報價並前往付款' : expired || failed ? '重新取得正式報價' : '取得正式報價'

  return <section aria-label="正式報價與確認" aria-busy={busy} className="border-t border-line pt-6">
    <div aria-live="polite" aria-atomic="true">
      {ready ? <>
        {!!quote.lineItems?.length && <dl className="mb-5 space-y-3 border-b border-line pb-5 text-sm">
          {quote.lineItems.map((item, index) => <div key={index} className="flex justify-between gap-4">
            <dt>{item.label}</dt><dd className="shrink-0">{money(item.amount)}</dd>
          </div>)}
        </dl>}
        <div className="md:text-right">
          <p className="text-sm">正式總價</p>
          <p className="mt-2 text-2xl font-bold text-ink md:text-[28px]">{money(quote.total)}</p>
          <p className="mt-1 text-xs text-muted">台幣 TWD</p>
        </div>
      </> : <p className={`text-sm md:text-right ${expired ? 'text-vermilion' : 'text-muted'}`}>
        {expired ? '報價已到期，請重新取得正式報價。' : failed ? '未能取得正式報價，請重試。' : '尚未取得正式報價'}
      </p>}
    </div>
    <p className="mt-4 text-xs leading-6 text-muted md:text-right">取得報價不會扣款。確認報價後，才會暫留商品與名額 10 分鐘，並進入信用卡付款。</p>
    <div className="mt-5 flex md:justify-end">
      <button type="button" disabled={busy || disabled} onClick={onAction}
        className="inline-flex min-h-11 w-auto items-center justify-center rounded-none border border-vermilion bg-vermilion px-6 py-3 text-sm text-white transition-colors hover:bg-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-vermilion disabled:cursor-not-allowed disabled:opacity-45">
        {label}
      </button>
    </div>
  </section>
}
