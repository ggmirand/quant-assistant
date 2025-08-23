import React, {useEffect, useMemo, useState} from 'react'
import { createRoot } from 'react-dom/client'

const Box = ({children, title}) => (
  <div style={{border:'1px solid #e5e7eb', borderRadius:12, padding:16, margin:'16px 0'}}>
    <div style={{fontWeight:600, marginBottom:8}}>{title}</div>
    {children}
  </div>
)

function useFetch(url){
  const [data,setData]=useState(null), [err,setErr]=useState(null), [loading,setLoading]=useState(true)
  useEffect(()=>{ setLoading(true); fetch(url).then(r=>r.json()).then(d=>{setData(d);setLoading(false)}).catch(e=>{setErr(e);setLoading(false)}) },[url])
  return {data,err,loading}
}

function Table({rows, columns}){
  return <div style={{overflowX:'auto'}}>
    <table style={{width:'100%', borderCollapse:'collapse'}}>
      <thead style={{background:'#f9fafb'}}><tr>
        {columns.map(c=><th key={c.key} style={{textAlign:'left', padding:'10px 8px', fontSize:13, color:'#334155', borderBottom:'1px solid #e5e7eb'}}>{c.label}</th>)}
      </tr></thead>
      <tbody>
        {rows.map((r,i)=><tr key={i} style={{borderBottom:'1px solid #f1f5f9'}}>
          {columns.map(c=><td key={c.key} style={{padding:'10px 8px', fontSize:13}}>{c.render? c.render(r[c.key], r): r[c.key]}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>
}

function App(){
  const [symbols,setSymbols]=useState("AAPL,MSFT,NVDA,TSLA,AMZN")
  const sectors = useFetch("http://localhost:8000/api/screener/sectors")
  const [scan,setScan]=useState(null)
  const runScan=async()=>{
    const u=new URL("http://localhost:8000/api/screener/scan")
    u.searchParams.set("symbols",symbols); u.searchParams.set("min_volume","1000000")
    const r=await fetch(u); setScan(await r.json())
  }
  const columns = useMemo(()=>[
    {key:'symbol', label:'Symbol'},
    {key:'price', label:'Price', render:v=>Number(v).toFixed(2)},
    {key:'volume', label:'Volume'},
    {key:'ema_short', label:'EMA(12)', render:v=>Number(v).toFixed(2)},
    {key:'ema_long', label:'EMA(26)', render:v=>Number(v).toFixed(2)},
    {key:'rsi', label:'RSI', render:v=>Number(v).toFixed(1)},
    {key:'signals', label:'Signals', render:(v)=> <div>
      {v.trend_up && <span style={{color:'#16a34a'}}>Trend↑ </span>}
      {v.oversold && <span style={{color:'#0ea5e9'}}>Oversold </span>}
      {v.overbought && <span style={{color:'#dc2626'}}>Overbought </span>}
      {v.meets_min_volume && <span>Vol✓</span>}
    </div>}
  ],[])
  return <div style={{fontFamily:"Inter,system-ui",padding:24, maxWidth:1000, margin:'0 auto'}}>
    <h2 style={{marginBottom:6}}>Quant Assistant</h2>
    <div style={{color:'#64748b',fontSize:13, marginBottom:18}}>
      This UI is for education only — not financial advice.
    </div>

    <Box title="Sector performance">
      <pre style={{maxHeight:180, overflow:'auto', background:'#0b1221', color:'#00f7a7', padding:12, borderRadius:8}}>
        {sectors.loading? "Loading..." : JSON.stringify(sectors.data, null, 2)}
      </pre>
    </Box>

    <Box title="Quick screener">
      <div style={{display:'flex', gap:8, marginBottom:8}}>
        <input style={{flex:1, padding:'8px 10px', border:'1px solid #e5e7eb', borderRadius:8}} value={symbols} onChange={e=>setSymbols(e.target.value)} />
        <button onClick={runScan} style={{padding:'8px 12px', background:'#111827', color:'#fff', border:'none', borderRadius:8}}>Scan</button>
      </div>
      {scan?.results?.length ? <Table rows={scan.results} columns={columns} /> : <div style={{color:'#64748b'}}>No results yet.</div>}
    </Box>

    <Box title="Try Monte Carlo (curl)">
      <code>curl -X POST http://localhost:8000/api/simulator/monte-carlo -H "Content-Type: application/json" -d '{"symbol":"AAPL","days":30}'</code>
    </Box>

    <div style={{fontSize:12, color:'#64748b', marginTop:24}}>
      This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.
    </div>
  </div>
}
createRoot(document.getElementById('root')).render(<App/>)
