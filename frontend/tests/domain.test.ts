import { describe, expect, it } from 'vitest'
import { exampleBelts, examplePlans } from '../src/data/catalog'
import { estimatePrice, isPaidBooking, paymentLabel, localDate, participantsFor, safeReturnTo, secondsLeft, updateParticipant, validateParticipants } from '../src/lib/domain'

describe('最新商品與情侶規則', () => {
  const couple = examplePlans.find(p => p.kind === 'COUPLE')!
  it('雙人套餐建立兩個穩定角色，且沒有服裝尺寸欄位', () => {
    const people = participantsFor(couple)
    expect(people.map(p => p.role)).toEqual(['FEMALE', 'MALE'])
    expect(people.every(p => !('size' in p))).toBe(true)
  })
  it('修改女生照片不覆蓋男生照片', () => {
    const people = participantsFor(couple)
    const withMale = updateParticipant(people, 'male_1', { photoId: 'male-photo' })
    const withBoth = updateParticipant(withMale, 'female_1', { photoId: 'female-photo' })
    const replaced = updateParticipant(withBoth, 'female_1', { photoId: 'female-new' })
    expect(replaced.find(p => p.role === 'MALE')?.photoId).toBe('male-photo')
    expect(replaced.find(p => p.role === 'FEMALE')?.photoId).toBe('female-new')
  })
  it('切換男生角色時清除腰帶費來源', () => {
    const person = [{ id: 'one', role: 'FEMALE' as const, kimonoId: 'k1', beltId: exampleBelts[0].id }]
    expect(updateParticipant(person, 'one', { role: 'MALE' })[0].beltId).toBeNull()
  })
  it('拒絕男生挾帶配件與超過三人', () => {
    expect(() => validateParticipants([{ id: 'm', role: 'MALE', kimonoId: 'k', beltId: 'belt' }])).toThrow('男生無可選配件')
    expect(() => validateParticipants(Array.from({ length: 4 }, (_, i) => ({ id: String(i), role: 'FEMALE', kimonoId: '', beltId: null })))).toThrow('1～3')
  })
  it('拒絕重複人員識別，避免照片與和服串人', () => {
    const people = participantsFor(couple)
    expect(() => validateParticipants([people[0], people[0]])).toThrow('不可重複')
  })
  it('套餐底價只收一次，女生腰帶只加一次', () => {
    const people = updateParticipant(participantsFor(couple), 'female_1', { beltId: exampleBelts[0].id })
    expect(estimatePrice(couple, people, exampleBelts, false)).toBe(couple.price + exampleBelts[0].price)
  })
  it('不選腰帶沒有額外配件費', () => {
    expect(estimatePrice(couple, participantsFor(couple), exampleBelts, false)).toBe(couple.price)
  })
})

describe('交易與返回邊界', () => {
  it('沒有正式預約編號不能只靠 PAID 宣告完成', () => {
    expect(isPaidBooking({ orderNo: 'o1', paymentStatus: 'PAID', bookingNo: null })).toBe(false)
    expect(isPaidBooking({ orderNo: 'o1', paymentStatus: 'PAYMENT_PENDING', bookingNo: 'b1' })).toBe(false)
    expect(isPaidBooking({ orderNo: 'o1', paymentStatus: 'PAID', bookingNo: 'b1' })).toBe(true)
  })
  it('倒數依伺服器時間校正，而非直接信任會員裝置時間', () => {
    const receivedAt = Date.parse('2026-10-19T00:00:00Z')
    expect(secondsLeft('2026-10-19T01:10:00Z', '2026-10-19T01:00:00Z', receivedAt, receivedAt + 60_000)).toBe(540)
    expect(secondsLeft('2026-10-19T01:10:00Z', '2026-10-19T01:00:00Z', receivedAt, receivedAt + 600_000)).toBe(0)
  })
  it('登入返回只允許站內路徑', () => {
    expect(safeReturnTo('/booking?plan=couple')).toBe('/booking?plan=couple')
    for (const path of ['https://example.com', '//example.com', '/\\example.com', 'javascript:alert(1)', null]) expect(safeReturnTo(path)).toBe('/account')
  })
  it('日期使用日本門市時區的 yyyy-mm-dd 格式', () => {
    expect(localDate()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('授權與請款分開顯示', () => {
  it('只有後端正式預約編號才能將已授權訂單導向成功頁', () => {
    expect(isPaidBooking({orderNo:'o',paymentStatus:'AUTHORIZED'})).toBe(false)
    expect(isPaidBooking({orderNo:'o',paymentStatus:'AUTHORIZED',bookingNo:'b'})).toBe(true)
    expect(paymentLabel('AUTHORIZED')).toBe('已授權、待請款')
    expect(paymentLabel('PAID')).toBe('已請款')
  })
})
