import React from 'react'

export function SectorBar({rows=[], onBarClick}){
  // rows: [{sector, change}]
  if (!rows.length) return <div className="help">No sector data.</div>
  const max = Math.max(...rows.map(r=>Math.abs(r.change)||0), 1)
  return (
    <div className="card" role="group" aria-label="Sectors">
      {rows.map((r,i)=>{
        const w = Math.max(2, Math.round((Math.abs(r.change)/max)*100))
        const clr = r.change >= 0 ? 'var(--green)' : 'var(--danger)'
        return (
          <div key={i} className="row" style={{alignItems:'center', margin:'6px 0', cursor:'pointer'}}
               onClick={()=>onBarClick && onBarClick(r)}>
            <div style={{width:160}}>{r.sector}</div>
            <div style={{flex:'1 1 auto', background:'#1f2937', borderRadius:4, overflow:'hidden'}}>
              <div style={{height:10, width:`${w}%`, background:clr}} />
            </div>
            <div style={{width:70, textAlign:'right', marginLeft:8}}>{r.change.toFixed(2)}%</div>
          </div>
        )
      })}
    </div>
  )
}

export function GainersBar({rows=[]}){
  // rows: [{ticker, price, change}]
  if (!rows.length) return <div className="help">No top gainers right now.</div>
  return (
    <div className="card" role="list" aria-label="Top gainers">
      {rows.map((r,i)=>(
        <div key={i} className="row" role="listitem" style={{alignItems:'center', margin:'6px 0'}}>
          <div style={{width:80, fontWeight:600}}>{r.ticker}</div>
          <div style={{width:90}}>${Number(r.price).toFixed(2)}</div>
          <div style={{color:'var(--green)', fontWeight:600}}>{r.change}</div>
        </div>
      ))}
    </div>
  )
}

export function Histogram({values=[], bins=20, color='#60a5fa', title='Histogram'}){
  if (!values.length) return <div className="help">No data</div>
  const min = Math.min(...values), max = Math.max(...values), w = max-min || 1
  const edges = Array.from({length: bins+1}, (_,i)=> min + (i/bins)*w)
  const counts = new Array(bins).fill(0)
  for (const v of values){
    let idx = Math.min(bins-1, Math.max(0, Math.floor(((v-min)/w) * bins)))
    counts[idx]++
  }
  const maxC = Math.max(...counts, 1)
  return (
    <div className="card">
      <div className="help" style={{marginBottom:6}}>{title}</div>
      <svg width="100%" height="120" viewBox={`0 0 ${bins*6} 100`} preserveAspectRatio="none" role="img" aria-label="histogram">
        {counts.map((c,i)=>(
          <rect key={i} x={i*6} y={100 - (c/maxC)*100} width={5} height={(c/maxC)*100} fill={color}/>
        ))}
      </svg>
    </div>
  )
}
