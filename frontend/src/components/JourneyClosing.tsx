import { useId, useLayoutEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import '../home-closing.css'

// The same curve clips both the rings and the red surface in v75.
const wave = 'M0 150 C210 92 390 85 560 105 C850 140 1130 190 1410 125 C1630 65 1770 0 2048 12 L2048 5000 L0 5000 Z'
const cubic = (values: number[], t: number) => (1-t)**3*values[0]+3*(1-t)**2*t*values[1]+3*(1-t)*t*t*values[2]+t**3*values[3]
let low = 0, high = 1
for (let i=0;i<40;i++) {
  const t=(low+high)/2
  if(cubic([560,850,1130,1410],t)<1024) low=t
  else high=t
}
const centerWaveY=cubic([105,140,190,125],(low+high)/2)

export function JourneyClosing() {
  const sectionRef=useRef<HTMLElement>(null)
  const artworkRef=useRef<SVGSVGElement>(null)
  const actionsRef=useRef<HTMLDivElement>(null)
  const eyebrowRef=useRef<HTMLParagraphElement>(null)
  const id=useId()
  const waveId=id+'-wave', ringsMaskId=id+'-rings', surfaceMaskId=id+'-surface'

  useLayoutEffect(()=>{
    const section=sectionRef.current!, svg=artworkRef.current!, actions=actionsRef.current!, eyebrow=eyebrowRef.current!
    let frame=0, active=true
    const update=()=>{
      const width=section.clientWidth
      if(!active||!width)return
      const scale=width/2048, units=1/scale
      const buttons=Array.from(actions.children).map(element=>element.getBoundingClientRect())
      const buttonHeight=Math.max(...buttons.map(rect=>rect.height))
      const padding=(buttonHeight*1.9+(160-centerWaveY)*scale).toFixed(3)+'px'
      if(section.style.paddingBottom!==padding)section.style.paddingBottom=padding
      const rect=section.getBoundingClientRect()
      const top=Math.min(...buttons.map(button=>button.top))-rect.top
      const bottom=Math.max(...buttons.map(button=>button.bottom))-rect.top
      svg.setAttribute('viewBox',`0 0 2048 ${rect.height*units}`)
      svg.querySelector('[data-ring-cut]')!.setAttribute('transform',`translate(0 ${(top-buttonHeight*.58)*units-centerWaveY})`)
      svg.querySelector('[data-surface-cut]')!.setAttribute('transform',`translate(0 ${(bottom+buttonHeight*1.9)*units-centerWaveY})`)
      const ringSize=parseFloat(getComputedStyle(section).getPropertyValue('--closing-ring-size'))
      const ringTop=eyebrow.getBoundingClientRect().top-rect.top-27
      svg.querySelectorAll<SVGCircleElement>('[data-ring-inset]').forEach(circle=>{
        circle.setAttribute('cy',String((ringTop+ringSize/2)*units))
        circle.setAttribute('r',String((ringSize/2-Number(circle.dataset.ringInset))*units))
      })
    }
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(update)}
    const observer=new ResizeObserver(schedule)
    observer.observe(section)
    observer.observe(actions)
    window.addEventListener('resize',schedule,{passive:true})
    const image=section.querySelector('img')!
    image.addEventListener('load',schedule)
    document.fonts.ready.then(()=>{if(active)schedule()})
    update()
    return ()=>{active=false;cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('resize',schedule);image.removeEventListener('load',schedule)}
  },[])

  return <section id="journey-closing" ref={sectionRef} aria-labelledby="journey-closing-title">
    <p className="closing-eyebrow" ref={eyebrowRef}>TOKYO · KYOTO · YOUR STORY</p>
    <h2 id="journey-closing-title"><img src="/assets/kinu-tabi-brush-wordmark.png" alt="KINU TABI" /></h2>
    <p className="closing-message">準備好穿上你的日本旅程了嗎？</p>
    <div className="closing-actions" ref={actionsRef}><Link className="closing-primary" to="/booking">開始規劃體驗</Link><Link className="closing-secondary" to="/plans">再看看方案</Link></div>
    <svg id="closing-artwork" ref={artworkRef} viewBox="0 0 2048 700" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <defs>
        <path id={waveId} d={wave}/>
        <mask id={ringsMaskId} maskUnits="userSpaceOnUse" x="0" y="0" width="2048" height="5000" style={{maskType:'luminance'}}><rect width="2048" height="5000" fill="white"/><use data-ring-cut="" href={'#'+waveId} fill="black" transform="translate(0 350)"/></mask>
        <mask id={surfaceMaskId} maskUnits="userSpaceOnUse" x="0" y="0" width="2048" height="5000" style={{maskType:'luminance'}}><rect width="2048" height="5000" fill="white"/><use data-surface-cut="" href={'#'+waveId} fill="black" transform="translate(0 540)"/></mask>
      </defs>
      <rect width="2048" height="5000" fill="#a64036" mask={`url(#${surfaceMaskId})`}/>
      <g mask={`url(#${ringsMaskId})`} fill="none" stroke="#f2eee4">
        <circle data-ring-inset="0" cx="1024" cy="338" r="260" strokeOpacity=".25" vectorEffect="non-scaling-stroke"/>
        <circle data-ring-inset="30" cx="1024" cy="338" r="224" strokeOpacity=".15" vectorEffect="non-scaling-stroke"/>
        <circle data-ring-inset="65" cx="1024" cy="338" r="183" strokeOpacity=".15" vectorEffect="non-scaling-stroke"/>
      </g>
    </svg>
  </section>
}
