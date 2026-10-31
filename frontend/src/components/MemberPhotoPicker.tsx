import { useEffect, useRef, useState } from 'react'
import { Button, Check, Empty, Loading, Notice } from './ui'

export type MemberPhoto = { photoId:string; status:string; previewUrl?:string; issues?:{message:string}[] }

function PhotoPreview({photo,alt,className}: {photo:MemberPhoto;alt:string;className:string}) {
  const [src,setSrc]=useState(photo.previewUrl)
  const [failed,setFailed]=useState(false)
  useEffect(()=>{
    // A new signature does not change the photo. Use it only if the current URL fails.
    if((failed||!src)&&photo.previewUrl!==src){setSrc(photo.previewUrl);setFailed(false)}
  },[photo.previewUrl,src,failed])
  return <img src={src} alt={alt} className={className} onError={()=>setFailed(true)}/>
}

export function MemberPhotoPicker({photos,selectedId,label,loading,busy,validating=false,canUpload,consent,onConsent,onSelect,onUpload,onDelete}: {
  photos:MemberPhoto[]; selectedId?:string; label:string; loading:boolean; busy:boolean; canUpload:boolean; consent:boolean
  validating?:boolean
  onConsent:(value:boolean)=>void; onSelect:(photo:MemberPhoto)=>void
  onUpload:(file:File,replaceId?:string)=>void; onDelete:(photoId:string)=>void
}) {
  const input=useRef<HTMLInputElement>(null)
  const replacement=useRef<string|undefined>(undefined)
  const selected=photos.find(p=>p.photoId===selectedId)
  function chooseFile(replaceId?:string){replacement.current=replaceId;input.current?.click()}
  return <div className="space-y-4">
    <p className="text-xs leading-6 text-muted">會員共用照片庫 {photos.length} / 3 張。每位旅客可分別選用人物照片；新照片驗證成功後才替換舊圖。</p>
    <p className="text-sm font-semibold leading-7 text-red-700">請使用單人全身照，讓雙肩、髖部、膝蓋與腳踝清楚入鏡，避免遮擋。新照片通過人物與身體範圍檢查後才能使用。</p>
    {busy&&<p role="status" className="text-sm">{validating?'正在檢查人物與姿勢…':'正在處理照片…'}</p>}
    {loading&&!photos.length?<Loading/>:!photos.length?<Empty>尚未保存人物照片，請新增一張單人正面全身照。</Empty>:<div className="grid grid-cols-3 gap-2">
      {photos.map((photo,index)=><div key={photo.photoId} className="min-w-0 space-y-2">
        <button type="button" aria-label={'選用人物照片 '+(index+1)} aria-pressed={selectedId===photo.photoId} disabled={busy}
          onClick={()=>onSelect(photo)} className={'w-full border p-1 '+(selectedId===photo.photoId?'border-forest ring-1 ring-forest':'border-line')}>
          <PhotoPreview photo={photo} alt={'人物照片 '+(index+1)} className="aspect-[2/3] w-full object-contain"/>
          <span className="mt-1 block text-xs">{selectedId===photo.photoId?'已選取':'照片 '+(index+1)}</span>
        </button>
        <button type="button" disabled={busy||!canUpload||!consent} onClick={()=>chooseFile(photo.photoId)} className="min-h-11 w-full text-xs underline disabled:opacity-40">替換此照片</button>
        <button type="button" disabled={busy||!canUpload} onClick={()=>onDelete(photo.photoId)} className="min-h-11 w-full text-xs text-vermilion underline disabled:opacity-40">刪除照片</button>
      </div>)}
    </div>}
    {selected&&<PhotoPreview key={selected.photoId} photo={selected} alt={label+'選用的人物照片預覽'} className="block h-auto max-h-[360px] w-auto max-w-full object-contain"/>}
    <Check checked={consent} disabled={busy||!canUpload} onChange={e=>onConsent(e.target.checked)}>新增或替換照片時，我確認已取得照片當事人同意，並同意上述人物照片處理說明。</Check>
    <input ref={input} type="file" aria-label={label+'新增或替換人物照片'} className="sr-only"
      accept="image/jpeg,image/png,image/heic,image/heif,.heic" disabled={busy||!canUpload||!consent}
      onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)onUpload(file,replacement.current)}}/>
    <Button disabled={busy||!canUpload||!consent||photos.length>=3} onClick={()=>chooseFile()}>{busy?'照片上傳驗證中…':'新增照片'}</Button>
    {photos.length>=3&&<Notice>已達三張上限，請使用指定照片的「替換此照片」，或先刪除一張。</Notice>}
    <p className="text-[11px] leading-6 text-muted">JPEG / PNG / HEIC · 單張 10 MB 以內 · 長邊 1200～6000 像素</p>
  </div>
}
