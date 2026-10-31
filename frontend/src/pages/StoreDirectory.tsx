import { useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { ButtonLink, Container, Eyebrow, Loading, Notice } from '../components/ui'
import { useResource } from '../lib/hooks'
import '../store-directory.css'

export type Store = { id: string; name: string; city: string; address?: string; transport?: string; hours?: string; imageUrl?: string }

const cities = [
  { id: 'tokyo', name: '東京・淺草', label: '東京', image: 'kimono-shrine.jpg', description: '從淺草出發，安排一趟東京和服散策。' },
  { id: 'kyoto', name: '京都・祇園', label: '京都', image: 'kimono-couple.jpg', description: '從祇園出發，感受京都街道的和服風景。' },
] as const
const emptyStores: Store[] = []

export function StoreDirectory() {
  const [params, setParams] = useSearchParams()
  const openCities = new Set(params.getAll('city'))
  const data = useResource<Store[] | Store>('/api/stores', emptyStores)
  const rows = Array.isArray(data.data) ? data.data : data.data ? [data.data] : []

  function toggleCity(city: string) {
    const nextOpen = new Set(openCities)
    if (nextOpen.has(city)) nextOpen.delete(city)
    else nextOpen.add(city)
    const next = new URLSearchParams(params)
    next.delete('city')
    cities.forEach(item => { if (nextOpen.has(item.id)) next.append('city', item.id) })
    setParams(next, { preventScrollReset: true })
  }

  return <section className="border-y border-line bg-wash/50">
    <Container>
      <Eyebrow>TOKYO & KYOTO</Eyebrow>
      <h1 className="mt-5 font-serif text-3xl md:text-[42px]">選一座城市，開始散策</h1>
      <div className="mt-10 grid items-start gap-6 md:grid-cols-2">
        {cities.map(city => {
          const expanded = openCities.has(city.id)
          const titleId = 'store-city-' + city.id
          const detailsId = 'store-info-' + city.id
          const stores = rows.filter(store => store.city.toLowerCase() === city.id)
          const coverStore = stores.find(store => store.imageUrl)
          return <article key={city.id} aria-labelledby={titleId} className="border border-line">
            <div className="grid grid-cols-[.9fr_1fr]">
              <img src={coverStore?.imageUrl ?? '/assets/' + city.image} alt={coverStore ? coverStore.name + '門市照片' : city.name + '風格參考，非正式店內照片'} className="h-full min-h-60 w-full object-cover md:aspect-[2/3]" />
              <div className="flex flex-col items-start justify-center p-5 md:p-7">
                <h2 id={titleId} className="font-serif text-xl">{city.name}</h2>
                <p className="mt-3 text-xs leading-7 text-muted">{city.description}</p>
                <button type="button" aria-controls={detailsId} aria-expanded={expanded} onClick={() => toggleCity(city.id)} className="store-city-toggle mt-5">
                  {expanded ? '收合門市資訊' : '查看' + city.label + '門市'}
                  {expanded ? <ChevronUp size={16} strokeWidth={1.5} /> : <ChevronDown size={16} strokeWidth={1.5} />}
                </button>
              </div>
            </div>
            <section id={detailsId} aria-labelledby={titleId} hidden={!expanded} className="border-t border-line p-5 md:p-7">
              {data.loading ? <Loading /> : data.error ? <Notice tone="error">{data.error}</Notice> : !stores.length ? <div className="text-sm leading-8 text-muted">
                <p>{city.label}門市資訊準備中</p>
                <p>地址、交通與營業時間將於資料確認後顯示。</p>
              </div> : <div className="space-y-6 divide-y divide-line">
                {stores.map(store => <div key={store.id} className="pt-6 first:pt-0">
                  {store.imageUrl && <img src={store.imageUrl} alt={store.name} className="mb-6 aspect-video w-full object-cover" />}
                  <h3 className="font-serif text-xl">{store.name}</h3>
                  <dl className="mt-5 space-y-4 text-sm leading-8">
                    <div><dt className="font-medium">地址</dt><dd className="text-muted">{store.address ?? '正式地址待補'}</dd></div>
                    <div><dt className="font-medium">交通方式</dt><dd className="text-muted">{store.transport ?? '交通資訊待補'}</dd></div>
                    <div><dt className="font-medium">營業時間</dt><dd className="text-muted">{store.hours ?? '營業時間待補'}</dd></div>
                  </dl>
                  <div className="mt-6"><ButtonLink primary to={'/booking?storeId=' + store.id}>選此門市預約</ButtonLink></div>
                </div>)}
              </div>}
            </section>
          </article>
        })}
      </div>
    </Container>
  </section>
}
