import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemberPhotoPicker } from '../src/components/MemberPhotoPicker'

const props = {
  selectedId: 'photo-1', label: '女生', loading: false, busy: false, canUpload: true, consent: true,
  onConsent() {}, onSelect() {}, onUpload() {}, onDelete() {},
  photos: [{ photoId: 'photo-1', status: 'READY', previewUrl: 'https://example.com/photo?signed=1' }],
}

describe('人物照片庫背景更新', () => {
  it('已載入照片時，背景更新不以載入畫面替換縮圖與選用預覽', () => {
    const loaded = renderToStaticMarkup(<MemberPhotoPicker {...props} />)
    const refreshing = renderToStaticMarkup(<MemberPhotoPicker {...props} loading />)
    expect(refreshing).toBe(loaded)
    expect(refreshing.match(/<img /g)).toHaveLength(2)
  })

  it('首次載入仍顯示載入提示，照片移除後不保留舊預覽', () => {
    const initial = renderToStaticMarkup(<MemberPhotoPicker {...props} photos={[]} loading />)
    expect(initial).toContain('載入中…')
    expect(initial).not.toContain('<img ')
    const removed = renderToStaticMarkup(<MemberPhotoPicker {...props} photos={[]} />)
    expect(removed).toContain('尚未保存人物照片')
    expect(removed).not.toContain('<img ')
  })
})
