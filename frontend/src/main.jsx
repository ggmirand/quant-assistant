import React, {useEffect, useMemo, useState, useRef} from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import { SectorBar, GainersBar, Histogram } from './charts.jsx'
import PriceVolume from './PriceVolume.jsx'
import PayoffChart from './PayoffChart.jsx'
import Glossary from './Glossary.jsx'

const Panel = ({title, children, desc, id}) => (
  <section className="panel" aria-labelledby={id}>
    <h3 id={id}>{title}</h3>
    {desc && <div className="help" style={{marginBottom:8}}>{desc}</div>}
    {children}
  </section>
)

function useFetch(url){
  const [data,setData]=useState(null), [err,setErr]=useState(null), [loading,setLoading]=useState(true)
  useEffect(()=>{ let alive=true;
    setLoading(true)
    fetch(url).then(r=>r.json()).then(d=>{ if(alive){ setData(d); setLoading(false) } })
    .catch(e=>{ if(alive){ setErr(e); setLoading(false) } })
    return ()=>{ alive=false }
  },[url])
  return {data,err,loading}
}

function Table({rows, columns, caption}){
  if (!rows?.length) return <div className="help">No rows.</div>
  return (
    <div className="table-wrap">
      <table role="table">
        {caption && <caption className="help" style={{textAlign:'left', marginBottom:6}}>{caption}</caption>}
        <thead><tr>{columns.map(c=><th key={c.key} scope="col">{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r,i)=>
            <tr key={i}>{columns.map(c=><td key={c.key}>{c.render? c.render(r[c.key], r): r[c.key]}</td>)}</tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function Sparkline({data=[], width=100, height=26, color='var(--accent)', strokeWidth=2, title='Sparkline'}){
  if (!data || data.length < 2) return <span className="help">—</span>
  const min = Math.min(...data), max = Math.max(...data)
  const h = height, w = width
  const xs = data.map((_,i)=> (i/(data.length-1))*w)
  const ys = data.map(v => max===min? h/2 : h - ((v-min)/(max-min))*h )
  const d = xs.map((x,i)=> (i===0?`M ${x.toFixed(1)},${ys[i].toFixed(1)}`:`L ${x.toFixed(1)},${ys[i].toFixed(1)}`)).join(' ')
  return <svg width={w} height={h} role="img" aria-label={title}><path d={d} fill="none" stroke={color} strokeWidth={strokeWidth} /></svg>
}

function DarkModeToggle(){
  const [isLight, setIsLight] = useState(false)
  useEffect(()=>{
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    const stored = localStorage.getItem('theme')
    const light = stored ? stored === 'light' : !prefersDark ? true : false
    setIsLight(light)
    document.documentElement.classList.toggle('light', light)
  },[])
  const toggle=()=>{
    const next = !isLight; setIsLight(next)
    document.documentElement.classList.toggle('light', next)
    localStorage.setItem('theme', next ? 'light' : 'dark')
  }
  return <button className="toggle" aria-pressed={isLight} onClick={toggle} title="Toggle color scheme">
    <span aria-hidden="true">{isLight ? '🌞' : '🌙'}</span> {isLight ? 'Light' : 'Dark'}
  </button>
}

function useAutoRefresh(callback, delayMs, enabled){
  const ref = useRef(()=>{})
  useEffect(()=>{ ref.current = callback }, [callback])
  useEffect(()=>{ if (!enabled || !delayMs || delayMs<1000) return;
    const id=setInterval(()=>ref.current(), delayMs); return ()=>clearInterval(id)
  },[delayMs, enabled])
}

function Card({children}){ return <div className="card" style={{flex:'1 1 380px', minWidth:320}}>{children}</div> }

function SuggestionCard({sug}){
  if (!sug || !sug.suggestion) return null
  const c = sug.suggestion
  return (
    <Card>
      <div style={{fontWeight:600, marginBottom:6}}>{sug.symbol}</div>
      <div className="help">Underlying price: <b>${Number(sug.under_price||0).toFixed(2)}</b></div>
      <div className="help">Contract: <b>{c.type}</b> | Exp: <b>{c.expiry}</b> | Strike: <b>${Number(c.strike).toFixed(2)}</b></div>
      <div className="help">Premium (mid): <b>${Number(c.mid_price).toFixed(2)}</b> | Breakeven: <b>${Number(c.breakeven).toFixed(2)}</b></div>
      <div className="help">Δ: <b>{(c.delta??0).toFixed(2)}</b> | IV: <b>{(Number(c.iv||0)*100).toFixed(1)}%</b> | Chance of profit: <b>{(Number(c.chance_profit||0)*100).toFixed(1)}%</b></div>
      <div className="help">Confidence: <b>{Number(sug.confidence||0)}</b> / 100 | Cost (1x): <b>${Number(sug.cost_estimate||0).toFixed(2)}</b></div>

      <div className="help" style={{marginTop:8}}><b>Plain-English summary</b><br/>{sug.explanation}</div>
      <div className="help" style={{marginTop:6}}><b>Thought process</b></div>
      <ul className="help" style={{marginTop:4}}>
        {(sug.thought_process||[]).map((t,i)=><li key={i}>{t}</li>)}
      </ul>

      <div className="row" style={{marginTop:10}}>
        <div style={{flex:'1 1 420px', minWidth:260}}>
          <div className="help" style={{marginBottom:6}}>Payoff at expiry (1x)</div>
          <PayoffChart s0={sug.under_price} type={String(c.type).toUpperCase()} strike={Number(c.strike)} premium={Number(c.mid_price||0)} />
        </div>
        <div style={{flex:'1 1 420px', minWidth:260}}>
          <div className="help" style={{marginBottom:6}}>Simulated P/L distribution (samples)</div>
          {sug.sim?.samples?.length ? <Histogram values={sug.sim.samples} bins={20} color="#60a5fa" title="Sim P/L"/> : <div className="help">No simulation available</div>}
          {sug.sim && <div className="help" style={{marginTop:6}}>
            P5: <b>${sug.sim.pl_p5.toFixed(2)}</b> | Median: <b>${sug.sim.pl_p50.toFixed(2)}</b> | P95: <b>${sug.sim.pl_p95.toFixed(2)}</b> | P(profit): <b>{(sug.sim.prob_profit*100).toFixed(1)}%</b>
          </div>}
        </div>
      </div>
    </Card>
  )
}

function App(){
  // API status
  const [apiOk,setApiOk]=useState(null)
  useEffect(()=>{ fetch("http://localhost:8000/health").then(r=>r.json()).then(()=>setApiOk(true)).catch(()=>setApiOk(false)) },[])

  // Market Highlights (unchanged)
  const sectors = useFetch("http://localhost:8000/api/screener/sectors")
  const movers  = useFetch("http://localhost:8000/api/screener/top-movers")
  const topSectors = useMemo(()=>{
    const map = sectors.data?.["Rank A: Real-Time Performance"] || {}
    return Object.entries(map).map(([name,p])=>({sector:name, change: parseFloat(String(p).replace('%',''))}))
      .sort((a,b)=> b.change-a.change).slice(0,6)
  },[sectors.data])
  const topGainers = useMemo(()=> (movers.data?.top_gainers||[]).slice(0,8).map(x=>({ticker:x.ticker, price:x.price, change:x.change_percentage})), [movers.data])

  // Screener (kept for context)
  const [symbols,setSymbols]=useState("AAPL,MSFT,NVDA,TSLA,AMZN")
  const [scan,setScan]=useState(null)
  const runScan=async()=>{
    const u=new URL("http://localhost:8000/api/screener/scan")
    u.searchParams.set("symbols",symbols)
    u.searchParams.set("min_volume","1000000")
    u.searchParams.set("include_history","1")
    u.searchParams.set("history_days","180")
    const r=await fetch(u); setScan(await r.json())
  }
  const scanCols = [
    {key:'symbol',label:'Symbol'},
    {key:'price',label:'Price', render:v=>Number(v).toFixed(2)},
    {key:'rsi',label:'RSI', render:v=>Number(v).toFixed(1)},
    {key:'mom_5d',label:'5d %', render:v=> isNaN(v)?'—':(Number(v)*100).toFixed(1)+'%'},
    {key:'volume',label:'Volume'},
    {key:'closes',label:'Spark', render:(v,r)=> <Sparkline data={r.closes} width={100} height={26} title={`${r.symbol} recent closes`}/>},
  ]

  // ---------- Options: My Ticker ----------
  const [mySym,setMySym]=useState("AAPL")
  const [myBP,setMyBP]=useState(5000)
  const [myIdea,setMyIdea]=useState(null)
  const [myAuto,setMyAuto]=useState(true)
  const [myEvery,setMyEvery]=useState(30000) // default 30s to avoid rate-limit

  const fetchMyIdea=async()=>{
    const u=new URL("http://localhost:8000/api/options/idea")
    u.searchParams.set("symbol", mySym)
    u.searchParams.set("buying_power", String(myBP))
    const r=await fetch(u); const j=await r.json(); setMyIdea(j)
  }
  useEffect(()=>{ fetchMyIdea() },[])
  useAutoRefresh(fetchMyIdea, myEvery, myAuto)
  useEffect(()=>{
    if (myIdea?.note && /429|rate limited/i.test(String(myIdea.note))) {
      setMyEvery(60000); const t=setTimeout(()=>setMyEvery(30000), 60_000); return ()=>clearTimeout(t)
    }
  },[myIdea?.note])

  // ---------- Options: Market Scan For Me ----------
  const [scanBP,setScanBP]=useState(3000)
  const [scanIdeas,setScanIdeas]=useState(null)
  const [scanNote,setScanNote]=useState(null)
  const runScanIdeas=async()=>{
    const r = await fetch("http://localhost:8000/api/options/scan-ideas", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({buying_power: Number(scanBP)})
    })
    const j=await r.json(); setScanIdeas(j.ideas||[]); setScanNote(j.note||null)
  }
  useEffect(()=>{ runScanIdeas() },[]) // run once on load

  return (
    <div className="container">
      <header className="header">
        <div style={{display:'flex', gap:10, alignItems:'center'}}>
          <h2 style={{margin:0}}>Quant Assistant</h2>
          <span className="badge" aria-live="polite">
            <span className={`dot ${apiOk==null?'':(apiOk?'ok':'err')}`} /> API: {apiOk==null?'checking…':(apiOk?'OK':'down')}
          </span>
        </div>
        <DarkModeToggle />
      </header>
      <div className="help" style={{marginBottom:12}}>
        This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.
      </div>

      {/* MARKET */}
      <Panel id="highlights" title="Market Highlights" desc="Top sectors & highest‑performing stocks (% change).">
        <div className="row">
          <div style={{flex:'1 1 420px', minWidth:320}}>
            <div className="help" style={{marginBottom:6}}>Sector performance</div>
            <SectorBar rows={topSectors}/>
          </div>
          <div style={{flex:'1 1 420px', minWidth:320}}>
            <div className="help" style={{marginBottom:6}}>Top gainers</div>
            <GainersBar rows={topGainers}/>
          </div>
        </div>
      </Panel>

      {/* SCREENER (existing, lightweight) */}
      <Panel id="screener" title="Quick Screener" desc="Fetches recent stats for a list of tickers.">
        <form className="row" onSubmit={(e)=>{e.preventDefault();runScan()}}>
          <div className="input" style={{flex:'1 1 520px'}}>
            <label htmlFor="tickers">Tickers (comma‑separated)</label>
            <input id="tickers" value={symbols} onChange={e=>setSymbols(e.target.value)} />
          </div>
          <div className="input">
            <button className="button" type="submit">Scan</button>
          </div>
        </form>
        <Table rows={(scan?.results||[]).slice(0,10)} columns={scanCols} caption="First 10 rows"/>
      </Panel>

      {/* OPTIONS — My Ticker */}
      <Panel id="myticker" title="Options — My Ticker (automated filters)" desc="We pick a single best contract using liquidity, Δ≈0.30, DTE 21–45, affordability, and trend alignment.">
        <form className="row" onSubmit={(e)=>{e.preventDefault();fetchMyIdea()}}>
          <div className="input">
            <label htmlFor="mysym">Symbol</label>
            <input id="mysym" value={mySym} onChange={e=>setMySym(e.target.value.toUpperCase())}/>
          </div>
          <div className="input">
            <label htmlFor="mybp">Buying power ($)</label>
            <input id="mybp" type="number" min="0" inputMode="numeric" value={myBP} onChange={e=>setMyBP(e.target.value)}/>
          </div>
          <div className="input">
            <button className="button" type="submit">Get idea</button>
          </div>
          <div className="input">
            <label>Auto</label>
            <div style={{display:'flex', gap:8, alignItems:'center'}}>
              <input type="checkbox" checked={myAuto} onChange={e=>setMyAuto(e.target.checked)} />
              <input type="number" min="10" step="5" value={Math.round(myEvery/1000)} onChange={e=>setMyEvery(Number(e.target.value)*1000)} style={{width:80}}/>
              <span className="help">sec</span>
            </div>
          </div>
        </form>

        {myIdea?.note && <div role="alert" className="help" style={{color:'var(--danger)', marginTop:8}}>{String(myIdea.note)}</div>}
        {myIdea?.suggestion ? <SuggestionCard sug={myIdea}/> : <div className="help" style={{marginTop:8}}>No suggestion yet.</div>}
      </Panel>

      {/* OPTIONS — Market Scan For Me */}
      <Panel id="scanme" title="Options — Market Scan For Me" desc="We scan a large‑cap universe and return up to 3 ideas using the same automated filters.">
        <form className="row" onSubmit={(e)=>{e.preventDefault();runScanIdeas()}}>
          <div className="input">
            <label htmlFor="scanbp">Buying power ($)</label>
            <input id="scanbp" type="number" min="0" inputMode="numeric" value={scanBP} onChange={e=>setScanBP(e.target.value)}/>
          </div>
          <div className="input">
            <button className="button" type="submit">Scan for me</button>
          </div>
        </form>
        {scanNote && <div role="alert" className="help" style={{color:'var(--danger)'}}>{String(scanNote)}</div>}
        {(scanIdeas||[]).length ? (
          <div className="row" style={{marginTop:8}}>
            {scanIdeas.map((s,i)=><SuggestionCard key={i} sug={s} />)}
          </div>
        ) : <div className="help" style={{marginTop:8}}>No ideas yet.</div>}
      </Panel>

      <Glossary />
      <footer className="help" role="contentinfo" style={{marginTop:16}}>
        This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.
      </footer>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App/>)
