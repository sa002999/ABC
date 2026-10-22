import type { Belt, Plan } from '../lib/domain'

// Read-only examples for layout review. Never sent as real inventory or charged.
export const examplePlans: Plan[] = [
  { id: 'example-classic', name: '經典和服散策', city: 'kyoto', kind: 'SINGLE', role: 'FEMALE', price: 1900, image: '/assets/kimono-portrait.jpg', description: '在京都的巷弄裡，找到屬於自己的步調。' },
  { id: 'example-couple', name: '雙人和服・一起散策', city: 'kyoto', kind: 'COUPLE', role: 'FEMALE', price: 3600, image: '/assets/kimono-couple.jpg', description: '兩個人，兩套和服，一段共同收藏的旅程。' },
  { id: 'example-formal', name: '典雅和服體驗', city: 'tokyo', kind: 'SINGLE', role: 'FEMALE', price: 2800, image: '/assets/kimono-red.jpg', description: '細緻的紋樣，為值得記住的一天添上色彩。' },
  { id: 'example-male', name: '男士和服散策', city: 'tokyo', kind: 'SINGLE', role: 'MALE', price: 1900, image: '/assets/kimono-shrine.jpg', description: '簡練的搭配，在東京留下一段不一樣的日常。' },
]
export const exampleBelts: Belt[] = [
  { id: 'example-belt-ivory', name: '米白織紋腰帶', price: 200, category: 'BELT' },
  { id: 'example-belt-red', name: '朱紅花紋腰帶', price: 300, category: 'BELT' },
]
export const cities: Record<string, string> = { tokyo: '東京・淺草', kyoto: '京都・祇園' }
export const faq = [
  ['一定要先使用 AI 試穿嗎？', '不需要。AI 預覽與收藏都是選用功能，可以直接選方案並預約。'],
  ['和服需要選尺寸嗎？', '所有和服統一尺寸，不需選擇 S、M 或 L。AI 圖像僅供款式與配色參考，不保證實際合身度。'],
  ['有哪些配件可以選擇？', '女生可選配件僅腰帶，男生沒有可選配件。其他照片中的裝飾僅供示意，不提供加購；實際包含內容依方案顯示。'],
  ['情侶方案可以上傳兩人的照片嗎？', '可以。女生、男生各有獨立上傳位置，分別選擇、替換與刪除照片，不會互相覆蓋。'],
  ['可以預約幾個人？', '每筆預約可安排 1～3 人，情侶方案計兩名旅客。同門市、同時段，各自配置和服，整筆付款。'],
  ['臨時無法前往，可以取消嗎？', '以日本場次時間計算：開始前超過 7×24 小時取消可全退，等於或少於不退；改期需取消原單後另訂。'],
]
