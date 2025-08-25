import React from 'react'

export default function PriceVolume({closes=[], volumes=[]}) {
  if (!closes?.length) return <div className="help">No data</div>
  const labels = Array.from({length: closes.length}, (_,i)=> `-${closes.length-1-i}`)
  const maxVol = Math.max(...(volumes||[]), 1)
  const h = 92, w = 560
  const px = (i)=> (i/(closes.length-1))*w
  const minP = Math.min(...closes), maxP = Math.max(...closes)
  const py = (v)=> h - ( (v - minP) / Math.max(1e-9, (maxP - minP)) )*h
  const path = closes.map((v,i)=> (i===0?`M ${px(i)},${py(v)}`:`L ${px(i)},${py(v)}`)).join(' ')
  return (
    <div style={{display:'grid', gap:8}}>
      <svg width={w} height={h} role="img" aria-label="Price sparkline">
        <path d={path} fill="none" stroke="#60a5fa" strokeWidth="2" />
      </svg>
      {volumes?.length ? (
        <svg width={w} height="46" role="img" aria-label="Volume bars">
          {volumes.map((v,i)=> {
            const barH = Math.max(2, (v/maxVol)*40)
            return <rect key={i} x={px(i)} y={44-barH} width="4" height={barH} fill="#64748b"/>
          })}
        </svg>
      ) : null}
    </div>
  )
}
