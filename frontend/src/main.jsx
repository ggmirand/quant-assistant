import React, {useEffect, useMemo, useState} from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import { SectorBar, GainersBar, Histogram } from './charts'
import PriceVolume from './PriceVolume'

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

function Table({rows, columns, caption, onRowClick, getRowKey, getRowActive}){
  if (!rows?.length) return <div className="help">No rows.</div>
  return (
    <div className="table-wrap">
      <table role="table">
        {caption && <caption className="help" style={{textAlign:'left', marginBottom:6}}>{caption}</caption>}
        <thead><tr>{columns.map(c=>
          <th key={c.key} scope="col">{c.label}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((r,i)=>{
            const active = getRowActive ? getRowActive(r) : false
            return (
              <tr key={getRowKey? getRowKey(r) : i}
                  onClick={onRowClick? ()=>onRowClick(r) : undefined}
                  style={{cursor: onRowClick? 'pointer':'default', background: active ? 'rgba(0,200,5,0.08)':'transparent'}}>
                {columns.map(c=><td key={c.key}>{c.render? c.render(r[c.key], r): r[c.key]}</td>)}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// Tiny inline sparkline
function Sparkline({data=[], width=100, height=26, color='var(--accent)', strokeWidth=2, title='Sparkline'}){
  if (!data || data.length < 2) return <span className="help">—</span>
  const min = Math.min(...data), max = Math.max(...data)
  const h = height, w = width
  const xs = data.map((_,i)=> (i/(data.length-1))*w)
  const ys = data.map(v => {
    if (max === min) return h/2
    const t = (v - min)/(max - min)
    return h - t*h
  })
  const d = xs.map((x,i)=> (i===0?`M ${x.toFixed(1)},${ys[i].toFixed(1)}`:`L ${x.toFixed(1)},${ys[i].toFixed(1)}`)).join(' ')
  return (
    <svg width={w} height={h} role="img" aria-label={title} style={{display:'block'}}>
      <title>{title}</title>
      <path d={d} fill="none" stroke={color} strokeWidth={strokeWidth} />
    </svg>
  )
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

function App(){
  // API status
  const [apiOk,setApiOk]=useState(null)
  useEffect(()=>{
    fetch("http://localhost:8000/health").then(r=>r.json()).then(()=>setApiOk(true)).catch(()=>setApiOk(false))
  },[])

  // Market Highlights
  const sectors = useFetch("http://localhost:8000/api/screener/sectors")
  const movers = useFetch("http://localhost:8000/api/screener/top-movers")
  const topSectors = useMemo(()=>{
    const map = sectors.data?.["Rank A: Real-Time Performance"] || {}
    const arr = Object.entries(map).map(([name,p])=>{
      const n = parseFloat(String(p).replace('%','')); return {sector: name, change: n}
    }).sort((a,b)=> b.change - a.change)
    return arr.slice(0,6)
  },[sectors.data])
  const topGainers = useMemo(()=> (movers.data?.top_gainers||[]).slice(0,8).map(x=>({
    ticker: x.ticker, price: x.price, change: x.change_percentage
  })), [movers.data])

  // Screener (180d history for chart)
  const [symbols,setSymbols]=useState("AAPL,MSFT,NVDA,TSLA,AMZN")
  const [scan,setScan]=useState(null); const [scanErr,setScanErr]=useState(null); const [scanLoad,setScanLoad]=useState(false)
  const [selected,setSelected]=useState(null)
  const runScan=async()=>{
    setScanErr(null); setScanLoad(true)
    try{
      const u=new URL("http://localhost:8000/api/screener/scan")
      u.searchParams.set("symbols",symbols)
      u.searchParams.set("min_volume","1000000")
      u.searchParams.set("include_history","1")
      u.searchParams.set("history_days","180")
      const r=await fetch(u); setScan(await r.json()); setSelected(null)
    }catch(e){ setScanErr(String(e)) } finally { setScanLoad(false) }
  }
  const scanCols = [
    {key:'symbol', label:'Symbol'},
    {key:'score', label:'Score'},
    {key:'price', label:'Price', render:v=>Number(v).toFixed(2)},
    {key:'rsi', label:'RSI', render:v=>Number(v).toFixed(1)},
    {key:'mom_5d', label:'5d %', render:v=> isNaN(v)?'—':(Number(v)*100).toFixed(1)+'%'},
    {key:'volume', label:'Volume'},
    {key:'volume_rank_pct', label:'Vol pct', render:v=> (Number(v)*100).toFixed(0)+'%'},
    {key:'signals', label:'Signals', render:(v)=> <div>
      {v.trend_up && <span style={{color:'var(--ok)'}}>Trend↑ </span>}
      {v.oversold && <span style={{color:'#0ea5e9'}}>Oversold </span>}
      {v.overbought && <span style={{color:'var(--danger)'}}>Overbought </span>}
      {v.meets_min_volume && <span>Vol✓</span>}
    </div>},
    {key:'closes', label:'Spark', render:(v,r)=> <Sparkline data={r.closes} width={100} height={26} title={`${r.symbol} recent closes`} />},
  ]
  const scanRows = useMemo(()=>{
    const rows = scan?.results || []
    return [...rows].sort((a,b)=> (b.score ?? 0) - (a.score ?? 0))
  },[scan?.results])

  // Options
  const [optSymbol,setOptSymbol]=useState("AAPL")
  const [buying,setBuying]=useState(5000)
  const [opt,setOpt]=useState(null); const [optErr,setOptErr]=useState(null); const [optLoad,setOptLoad]=useState(false)
  const [optSelected, setOptSelected] = useState(null)
  const runOptions=async()=>{
    setOptErr(null); setOpt(null); setOptSelected(null); setOptLoad(true)
    try{
      const u=new URL("http://localhost:8000/api/options/best-trades")
      u.searchParams.set("symbol",optSymbol)
      u.searchParams.set("buying_power", String(buying))
      const r=await fetch(u); const j=await r.json(); setOpt(j)
    }catch(e){ setOptErr(String(e)) } finally { setOptLoad(false) }
  }
  const optCols = [
    {key:'expiry', label:'Expiry'},
    {key:'type', label:'Type'},
    {key:'strike', label:'Strike', render:v=>Number(v).toFixed(2)},
    {key:'delta', label:'Delta', render:v=>Number(v).toFixed(2)},
    {key:'iv', label:'IV', render:v=> (Number(v)*100).toFixed(1)+"%"},
    {key:'prob_finish_above_strike', label:'P(Sₜ>K)', render:v=> isNaN(v)? '—' : (Number(v)*100).toFixed(1)+"%"},
    {key:'mid_price', label:'Mid', render:v=>Number(v||0).toFixed(2)},
  ]

  // Options analysis helpers (no personal advice)
  function formatMoney(n){ return isFinite(n) ? `$${Number(n).toFixed(2)}` : '—' }
  function optionAnalysis(c){
    if(!c) return null
    const premium = Number(c.mid_price||0)
    const strike  = Number(c.strike||0)
    const type    = (c.type||'').toUpperCase()
    const probITM = isFinite(c.prob_finish_above_strike) ? Number(c.prob_finish_above_strike) : NaN
    const delta   = isFinite(c.delta) ? Number(c.delta) : NaN
    const iv      = isFinite(c.iv) ? Number(c.iv) : NaN

    // Breakeven at expiry (underlying at T) – approximate, without fees:
    // Call: S_T = strike + premium ; Put: S_T = strike - premium
    const breakeven = type === 'CALL' ? strike + premium : strike - premium

    // Simple explanatory fields
    const greeks = `Δ=${isNaN(delta)?'—':delta.toFixed(2)}  |  IV=${isNaN(iv)?'—':(iv*100).toFixed(1)}%`
    const probTxt = isNaN(probITM) ? '—' : `${(probITM*100).toFixed(1)}%`
    const payoff = type === 'CALL'
      ? `Max gain: unlimited above strike; Max loss: premium (${formatMoney(premium)}).`
      : `Max gain: strike − premium if stock goes to $0; Max loss: premium (${formatMoney(premium)}).`

    // Plain-English summary for HS student
    const summary = type === 'CALL'
      ? `This is a CALL. You pay ${formatMoney(premium)} now. If the stock ends above $${strike.toFixed(2)} on expiry, it’s “in‑the‑money.” The model’s chance of that happening is ${probTxt}. You break even if the stock finishes above $${breakeven.toFixed(2)}.`
      : `This is a PUT. You pay ${formatMoney(premium)} now. If the stock ends below $${strike.toFixed(2)} on expiry, it’s “in‑the‑money.” The model’s chance of that happening (equivalent to finishing below strike) is ${isNaN(probITM)?'—':((1-probITM)*100).toFixed(1)+'%'} if prob shown was for finishing above strike. You break even if the stock finishes below $${breakeven.toFixed(2)}.`

    return {
      premium, strike, type, breakeven,
      greeks, probTxt, payoff, summary
    }
  }
  const optInfo = optionAnalysis(optSelected || (opt?.candidates?.[0] ?? null))

  // Monte Carlo
  const [mcSymbol,setMcSymbol]=useState("AAPL")
  const [mcDays,setMcDays]=useState(30)
  const [mcPaths,setMcPaths]=useState(2000)
  const [mcBarrier,setMcBarrier]=useState("")
  const [mc,setMc]=useState(null); const [mcErr,setMcErr]=useState(null); const [mcLoad,setMcLoad]=useState(false)
  const runMC=async()=>{
    setMc(null); setMcErr(null); setMcLoad(true)
    try{
      const body = { symbol: mcSymbol, days: Number(mcDays), n_paths: Number(mcPaths) }
      if (mcBarrier !== "") body.barrier = Number(mcBarrier)
      const r = await fetch("http://localhost:8000/api/simulator/monte-carlo", {
        method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)
      })
      setMc(await r.json())
    }catch(e){ setMcErr(String(e)) } finally { setMcLoad(false) }
  }
  const mcValues = mc?.terminal_prices || []

  return (
    <div className="container">
      <header className="header" role="banner" aria-label="App header">
        <div style={{display:'flex', gap:10, alignItems:'center'}}>
          <h2 style={{margin:0}}>Quant Assistant</h2>
          <span className="badge" aria-live="polite">
            <span className={`dot ${apiOk==null?'':(apiOk?'ok':'err')}`} />
            API: {apiOk==null?'checking…':(apiOk?'OK':'down')}
          </span>
        </div>
        <DarkModeToggle />
      </header>
      <div className="help" style={{marginBottom:12}}>
        This dashboard is for education only — not financial advice.
      </div>

      {/* MARKET HIGHLIGHTS */}
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

      {/* SCREENER */}
      <Panel id="screener" title="Quick Screener" desc="Ranks by composite score (trend, volume %, RSI distance to 50, 5‑day momentum).">
        <form className="row" onSubmit={(e)=>{e.preventDefault();runScan()}} aria-describedby="screener-help">
          <div className="input" style={{flex: '1 1 520px'}}>
            <label htmlFor="tickers">Tickers (comma‑separated)</label>
            <input id="tickers" name="tickers" placeholder="AAPL,MSFT,NVDA…" value={symbols} onChange={e=>setSymbols(e.target.value)} />
            <div id="screener-help" className="help">Weights: +40 trend↑, +30 volume pct, +20 RSI closeness to 50, +10 5‑day momentum.</div>
          </div>
          <div className="input">
            <label htmlFor="scan-btn" className="sr-only">Run scan</label>
            <button id="scan-btn" type="submit" className="button">{scanLoad? 'Scanning…' : 'Scan'}</button>
          </div>
        </form>
        {scanErr && <div role="alert" className="help" style={{color:'var(--danger)'}}>{String(scanErr)}</div>}
        <Table
          caption="Ranked by composite score (desc)"
          rows={scanRows}
          columns={scanCols}
          onRowClick={setSelected}
          getRowKey={(r)=>r.symbol}
          getRowActive={(r)=> selected?.symbol===r.symbol}
        />
      </Panel>

      {/* DETAILS */}
      <Panel id="details" title="Selected — Details" desc="180‑day price + volume, plus quick stats from screener.">
        {selected ? (
          <div className="row" role="group" aria-label="Selected symbol details">
            <div style={{flex:'1 1 560px', minWidth:320}}>
              <div className="help" style={{marginBottom:6}}>
                {selected.symbol} — last {selected.closes?.length || 0} days (left=older → right=newer)
              </div>
              <PriceVolume closes={selected.closes || []} volumes={selected.volumes || []}/>
            </div>
            <div style={{flex:'1 1 280px', minWidth:260}}>
              <div className="card">
                <div style={{fontWeight:600, marginBottom:6}}>{selected.symbol}</div>
                <div className="help">Price: <b>{Number(selected.price).toFixed(2)}</b></div>
                <div className="help">RSI(14): <b>{Number(selected.rsi).toFixed(1)}</b></div>
                <div className="help">EMA(12) / EMA(26): <b>{Number(selected.ema_short).toFixed(2)}</b> / <b>{Number(selected.ema_long).toFixed(2)}</b></div>
                <div className="help">5‑day return: <b>{isNaN(selected.mom_5d)?'—':(Number(selected.mom_5d)*100).toFixed(1)+'%'}</b></div>
                <div className="help">Volume rank: <b>{(Number(selected.volume_rank_pct)*100).toFixed(0)}%</b></div>
                <div className="help">Signals:
                  {selected.signals.trend_up && <span style={{color:'var(--ok)'}}> Trend↑</span>}
                  {selected.signals.oversold && <span style={{color:'#0ea5e9'}}> Oversold</span>}
                  {selected.signals.overbought && <span style={{color:'var(--danger)'}}> Overbought</span>}
                  {selected.signals.meets_min_volume && <span> Vol✓</span>}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="help">Click a screener row to see details here.</div>
        )}
      </Panel>

      {/* OPTIONS */}
      <Panel id="options" title="Options — Best Trades (delta‑targeted)" desc="Targets ~0.25 |delta| ≤45 days; shows risk‑neutral probability of finishing above strike (N(d₂)).">
        <form className="row" onSubmit={(e)=>{e.preventDefault();runOptions()}}>
          <div className="input">
            <label htmlFor="optSymbol">Symbol</label>
            <input id="optSymbol" name="optSymbol" value={optSymbol} onChange={e=>setOptSymbol(e.target.value.toUpperCase())} placeholder="AAPL"/>
          </div>
          <div className="input">
            <label htmlFor="buying">Buying power ($)</label>
            <input id="buying" name="buying" inputMode="numeric" type="number" min="0" value={buying} onChange={e=>setBuying(e.target.value)} placeholder="5000"/>
          </div>
          <div className="input">
            <label htmlFor="opt-btn" className="sr-only">Find</label>
            <button id="opt-btn" type="submit" className="button">{optLoad? 'Finding…' : 'Find'}</button>
          </div>
        </form>
        {optErr && <div role="alert" className="help" style={{color:'var(--danger)'}}>{String(optErr)}</div>}
        <Table
          caption="Candidate contracts (educational)"
          rows={opt?.candidates || []}
          columns={optCols}
          onRowClick={setOptSelected}
          getRowKey={(r)=>`${r.expiry}-${r.type}-${r.strike}`}
          getRowActive={(r)=> optSelected && r.expiry===optSelected.expiry && r.type===optSelected.type && r.strike===optSelected.strike}
        />

        {/* Analysis block */}
        <div className="row" style={{marginTop:12}}>
          <div className="card" style={{flex:'1 1 420px', minWidth:300}}>
            <div style={{fontWeight:600, marginBottom:6}}>Contract analysis</div>
            {optInfo ? (
              <>
                <div className="help">Type: <b>{optInfo.type}</b> &nbsp; | &nbsp; Strike: <b>${optInfo.strike.toFixed(2)}</b> &nbsp; | &nbsp; Premium: <b>{(optInfo.premium).toFixed(2)}</b></div>
                <div className="help">Breakeven (expiry): <b>${optInfo.breakeven.toFixed(2)}</b></div>
                <div className="help">Greeks/IV: <b>{optInfo.greeks}</b></div>
                <div className="help">Prob. finish in‑the‑money: <b>{optInfo.probTxt}</b></div>
                <div className="help">Payoff: {optInfo.payoff}</div>
              </>
            ) : <div className="help">Select an option to see details.</div>}
          </div>

          <div className="card" style={{flex:'1 1 420px', minWidth:300}}>
            <div style={{fontWeight:600, marginBottom:6}}>Plain‑English summary</div>
            {optInfo ? (
              <div className="help">
                {optInfo.summary}
                <div style={{marginTop:6}}>
                  <i>In short:</i> you’re risking about <b>${(optInfo.premium).toFixed(2)}</b>. Your breakeven at expiry is <b>${optInfo.breakeven.toFixed(2)}</b>. The shown probability is a model estimate, not a guarantee.
                </div>
              </div>
            ) : <div className="help">Select an option to see a simple explanation.</div>}
          </div>
        </div>
      </Panel>

      {/* MONTE CARLO */}
      <Panel id="monte" title="Monte Carlo Simulator" desc="Simulates GBM; histogram shows terminal price distribution.">
        <form className="row" onSubmit={(e)=>{e.preventDefault(); runMC()}}>
          <div className="input">
            <label htmlFor="mcSymbol">Symbol</label>
            <input id="mcSymbol" name="mcSymbol" value={mcSymbol} onChange={e=>setMcSymbol(e.target.value.toUpperCase())} placeholder="AAPL"/>
          </div>
          <div className="input">
            <label htmlFor="mcDays">Horizon (days)</label>
            <input id="mcDays" name="mcDays" inputMode="numeric" type="number" min="1" value={mcDays} onChange={e=>setMcDays(e.target.value)} />
          </div>
          <div className="input">
            <label htmlFor="mcPaths">Paths</label>
            <input id="mcPaths" name="mcPaths" inputMode="numeric" type="number" min="100" step="100" value={mcPaths} onChange={e=>setMcPaths(e.target.value)} />
          </div>
          <div className="input">
            <label htmlFor="mcBarrier">Barrier (optional)</label>
            <input id="mcBarrier" name="mcBarrier" inputMode="numeric" type="number" value={mcBarrier} onChange={e=>setMcBarrier(e.target.value)} placeholder="e.g., 220"/>
          </div>
          <div className="input">
            <label htmlFor="mc-btn" className="sr-only">Simulate</label>
            <button id="mc-btn" type="submit" className="button">{mcLoad? 'Simulating…' : 'Simulate'}</button>
          </div>
        </form>
        {mc?.summary
          ? <>
              <div className="help" aria-live="polite" style={{marginBottom:8}}>
                <div>P5: <b>{mc.summary.p5.toFixed(2)}</b> | Median: <b>{mc.summary.p50.toFixed(2)}</b> | P95: <b>{mc.summary.p95.toFixed(2)}</b></div>
                <div>μ (ann): {(mc.summary.mu_ann*100).toFixed(2)}% | σ (ann): {(mc.summary.sigma_ann*100).toFixed(2)}%</div>
                {'prob_touch' in mc && <div>Prob. touch: {(mc.prob_touch*100).toFixed(1)}%</div>}
              </div>
              <Histogram values={mcValues} bins={20} title="Terminal prices (count)"/>
            </>
          : <div className="help">{mcLoad? 'Running…' : 'Enter inputs and run a simulation.'}</div>
        }
        {mcErr && <div role="alert" className="help" style={{color:'var(--danger)'}}>{String(mcErr)}</div>}
      </Panel>

      <footer className="help" role="contentinfo" style={{marginTop:16}}>
        This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.
      </footer>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App/>)
