import React, {useEffect, useMemo, useState, useRef} from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import { SectorBar, GainersBar } from './charts.jsx'
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

function useAutoRefresh(callback, delayMs, enabled){
  const savedCb = useRef(()=>{})
  useEffect(()=>{ savedCb.current = callback }, [callback])
  useEffect(()=>{
    if (!enabled || !delayMs || delayMs < 1000) return
    const id = setInterval(()=> savedCb.current(), delayMs)
    return ()=> clearInterval(id)
  },[delayMs, enabled])
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

  // Screener
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

  // Options (best trades) with auto-refresh
  const [optSymbol,setOptSymbol]=useState("AAPL")
  const [buying,setBuying]=useState(5000)
  const [opt,setOpt]=useState(null); const [optErr,setOptErr]=useState(null); const [optLoad,setOptLoad]=useState(false)
  const [optSelected, setOptSelected] = useState(null)
  const [underPrice, setUnderPrice] = useState(null)
  const [optAuto, setOptAuto] = useState(true)
  const [optEvery, setOptEvery] = useState(15000) // ms

  async function fetchUnderlyingPrice(sym){
    try{
      const u=new URL("http://localhost:8000/api/screener/scan")
      u.searchParams.set("symbols", sym)
      u.searchParams.set("include_history","0")
      const r=await fetch(u); const j=await r.json()
      const first = j?.results?.[0]
      if (first && isFinite(first.price)) setUnderPrice(Number(first.price))
    }catch(_) {}
  }
  const runOptions=async()=>{
    setOptErr(null); setOptLoad(true)
    try{
      const u=new URL("http://localhost:8000/api/options/best-trades")
      u.searchParams.set("symbol",optSymbol)
      u.searchParams.set("buying_power", String(buying))
      const r=await fetch(u); const j=await r.json(); setOpt(j)
      fetchUnderlyingPrice(optSymbol)
      setOptSelected(null)
    }catch(e){ setOptErr(String(e)) } finally { setOptLoad(false) }
  }
  useEffect(()=>{ runOptions() },[]) // initial
  useAutoRefresh(runOptions, optEvery, optAuto)

  // Backoff when rate-limited (429)
  useEffect(()=>{
    if (opt?.note && /429|rate limited/i.test(String(opt.note))) {
      setOptEvery(60000);
      const t = setTimeout(()=> setOptEvery(15000), 60_000);
      return ()=> clearTimeout(t);
    }
  }, [opt?.note]);

  function itmBadge(row){
    if (!underPrice || !row) return null
    const isCall = String(row.type).toUpperCase()==='CALL'
    const itm = isCall ? underPrice > row.strike : underPrice < row.strike
    return <span style={{
      padding:'2px 6px', border:'1px solid var(--border)', borderRadius:6,
      color: itm? 'var(--bg)' : 'var(--muted)',
      background: itm? 'var(--ok)' : 'transparent',
      marginLeft:6, fontSize:12
    }}>{itm?'ITM':'OTM'}</span>
  }
  const optCols = [
    {key:'expiry', label:'Expiry'},
    {key:'type', label:'Type', render:(v,r)=> <>{v}{itmBadge(r)}</>},
    {key:'strike', label:'Strike', render:v=>Number(v).toFixed(2)},
    {key:'mid_price', label:'Premium', render:v=>Number(v||0).toFixed(2)},
    {key:'delta', label:'Delta', render:v=> (v==null?'—':Number(v).toFixed(2))},
    {key:'iv', label:'IV', render:v=> (Number(v)*100).toFixed(1)+"%"},
    {key:'prob_finish_above_strike', label:'P(Sₜ>K)', render:v=> isNaN(v)? '—' : (Number(v)*100).toFixed(1)+"%"},
    {key:'breakeven', label:'Breakeven', render:v=> Number(v).toFixed(2)},
  ]
  function formatMoney(n){ return isFinite(n) ? `$${Number(n).toFixed(2)}` : '—' }
  function optionAnalysis(c){
    if(!c) return null
    const premium = Number(c.mid_price||0)
    const strike  = Number(c.strike||0)
    const type    = (c.type||'').toUpperCase()
    const probITM = isFinite(c.prob_finish_above_strike) ? Number(c.prob_finish_above_strike) : NaN
    const delta   = isFinite(c.delta) ? Number(c.delta) : NaN
    const iv      = isFinite(c.iv) ? Number(c.iv) : NaN
    const breakeven = Number(c.breakeven|| (type==='CALL' ? strike + premium : strike - premium))
    const greeks = `Δ=${isNaN(delta)?'—':delta.toFixed(2)}  |  IV=${isNaN(iv)?'—':(iv*100).toFixed(1)}%`
    const probTxt = isNaN(probITM) ? '—' : `${(probITM*100).toFixed(1)}%`
    const payoff = type === 'CALL'
      ? `Max gain: unlimited above strike; Max loss: premium (${formatMoney(premium)}).`
      : `Max gain: strike − premium if stock goes to $0; Max loss: premium (${formatMoney(premium)}).`
    const summary = type === 'CALL'
      ? `This is a CALL. You pay ${formatMoney(premium)} now. If the stock ends above $${strike.toFixed(2)} at expiry, it’s “in the money.” The model’s chance of that is ${probTxt}. You break even if it ends above $${breakeven.toFixed(2)}.`
      : `This is a PUT. You pay ${formatMoney(premium)} now. If the stock ends below $${strike.toFixed(2)} at expiry, it’s “in the money.” Finishing below the strike has chance ≈ ${isNaN(probITM)?'—':((1-probITM)*100).toFixed(1)+'%'}. Your breakeven is $${breakeven.toFixed(2)} (below).`
    return { premium, strike, type, breakeven, greeks, probTxt, payoff, summary }
  }

  // Portfolio suggestions (auto-refresh + backoff)
  const [pfJSON, setPfJSON] = useState(JSON.stringify({
    buying_power: 3000,
    goal: "directional",
    positions: [{symbol:"AAPL", shares: 12}, {symbol:"MSFT", shares: 5}]
  }, null, 2))
  const [pfResp, setPfResp] = useState(null)
  const [pfErr, setPfErr] = useState(null)
  const [pfLoad, setPfLoad] = useState(false)
  const [pfAuto, setPfAuto] = useState(true)
  const [pfEvery, setPfEvery] = useState(15000)

  const runPortfolio=async()=>{
    setPfErr(null); setPfLoad(true)
    try{
      const r = await fetch("http://localhost:8000/api/options/portfolio-suggestions", {
        method:"POST", headers:{"Content-Type":"application/json"}, body: pfJSON
      })
      const j = await r.json()
      setPfResp(j)
    }catch(e){ setPfErr(String(e)) } finally { setPfLoad(false) }
  }
  useEffect(()=>{ runPortfolio() },[]) // initial
  useAutoRefresh(runPortfolio, pfEvery, pfAuto)

  useEffect(()=>{
    if (pfResp?.note && /429|rate limited/i.test(String(pfResp.note))) {
      setPfEvery(60000);
      const t = setTimeout(()=> setPfEvery(15000), 60_000);
      return ()=> clearTimeout(t);
    }
  }, [pfResp?.note]);

  // UI helpers
  const scanRows = useMemo(()=> (scan?.results || []).sort((a,b)=> (b.score ?? 0) - (a.score ?? 0)), [scan?.results])

  return (
    <div className="container">
      <header className="header">
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
              </div>
            </div>
          </div>
        ) : (
          <div className="help">Click a screener row to see details here.</div>
        )}
      </Panel>

      {/* OPTIONS — Best trades */}
      <Panel id="options" title="Options — Best Trades (real chain, live)" desc="Real expiries/strikes via yfinance; ~0.25 |delta| within 7–45 DTE.">
        <form className="row" onSubmit={(e)=>{e.preventDefault();runOptions()}}>
          <div className="input">
            <label htmlFor="optSymbol">Symbol</label>
            <input id="optSymbol" value={optSymbol} onChange={e=>setOptSymbol(e.target.value.toUpperCase())} />
          </div>
          <div className="input">
            <label htmlFor="buying">Buying power ($)</label>
            <input id="buying" inputMode="numeric" type="number" min="0" value={buying} onChange={e=>setBuying(e.target.value)} />
          </div>
          <div className="input">
            <label htmlFor="opt-btn" className="sr-only">Find</label>
            <button id="opt-btn" type="submit" className="button">{optLoad? 'Finding…' : 'Find'}</button>
          </div>
          <div className="input">
            <label>Auto</label>
            <div style={{display:'flex', gap:8, alignItems:'center'}}>
              <input type="checkbox" checked={optAuto} onChange={e=>setOptAuto(e.target.checked)} />
              <input type="number" min="5" step="5" value={Math.round(optEvery/1000)} onChange={e=>setOptEvery(Number(e.target.value)*1000)} style={{width:80}}/>
              <span className="help">sec</span>
            </div>
          </div>
        </form>

        {/* Show provider/rate-limit note prominently */}
        {opt?.note && (
          <div role="alert" className="help" style={{color:'var(--danger)', marginBottom:8}}>
            {String(opt.note)}
          </div>
        )}

        {/* Candidates table */}
        <Table
          caption="Click a row to analyze"
          rows={opt?.candidates || []}
          columns={optCols}
          onRowClick={setOptSelected}
          getRowKey={(r)=>`${r.expiry}-${r.type}-${r.strike}`}
          getRowActive={(r)=> optSelected && r.expiry===optSelected.expiry && r.type===optSelected.type && r.strike===optSelected.strike}
        />

        {/* Analysis + Payoff */}
        {(() => {
          const c = optSelected || (opt?.candidates?.[0] ?? null)
          if (!c || !underPrice) return null
          const i = optionAnalysis(c)
          return (
            <div className="panel" style={{marginTop:12}}>
              <div className="row">
                <div className="card" style={{flex:'1 1 420px', minWidth:300}}>
                  <div style={{fontWeight:600, marginBottom:6}}>Contract analysis</div>
                  <div className="help">Type: <b>{i.type}</b> | Strike: <b>${i.strike.toFixed(2)}</b> | Premium: <b>{i.premium.toFixed(2)}</b></div>
                  <div className="help">Breakeven (expiry): <b>${i.breakeven.toFixed(2)}</b></div>
                  <div className="help">Greeks/IV: <b>{i.greeks}</b></div>
                  <div className="help">Prob. finish in‑the‑money: <b>{i.probTxt}</b></div>
                  <div className="help">Payoff: {i.payoff}</div>
                </div>
                <div className="card" style={{flex:'1 1 420px', minWidth:300}}>
                  <div style={{fontWeight:600, marginBottom:6}}>Plain‑English summary</div>
                  <div className="help">
                    {i.summary}
                    <div style={{marginTop:6}}>
                      <i>In short:</i> You risk about <b>${i.premium.toFixed(2)}</b>. Breakeven at expiry is <b>${i.breakeven.toFixed(2)}</b>. Probabilities are estimates.
                    </div>
                  </div>
                </div>
              </div>
              <h3 style={{marginTop:12, marginBottom:8}}>Payoff at expiry</h3>
              <div className="help" style={{marginBottom:6}}>Profit/Loss for a single long {String(c.type).toUpperCase()} at different stock prices on expiry.</div>
              <PayoffChart s0={underPrice} type={String(c.type).toUpperCase()} strike={Number(c.strike)} premium={Number(c.mid_price||0)} />
            </div>
          )
        })()}
      </Panel>

      {/* PORTFOLIO SUGGESTIONS (NEW) */}
      <Panel id="pf" title="Portfolio Option Suggestions (live, educational)" desc="Paste simple JSON + buying power. Returns 1–3 long-option ideas with quick MC P/L.">
        <form className="row" onSubmit={(e)=>{e.preventDefault();runPortfolio()}}>
          <div className="input" style={{flex:'1 1 520px'}}>
            <label htmlFor="pfjson">Portfolio JSON</label>
            <textarea id="pfjson" rows={8} style={{width:'100%', background:'#0b141f', color:'var(--text)', border:'1px solid var(--border)', borderRadius:10, padding:10}}
              value={pfJSON} onChange={e=>setPfJSON(e.target.value)} />
          </div>
          <div className="input">
            <label className="sr-only" htmlFor="pfBtn">Generate</label>
            <button id="pfBtn" className="button" type="submit">{pfLoad?'Working…':'Generate'}</button>
          </div>
          <div className="input">
            <label>Auto</label>
            <div style={{display:'flex', gap:8, alignItems:'center'}}>
              <input type="checkbox" checked={pfAuto} onChange={e=>setPfAuto(e.target.checked)} />
              <input type="number" min="5" step="5" value={Math.round(pfEvery/1000)} onChange={e=>setPfEvery(Number(e.target.value)*1000)} style={{width:80}}/>
              <span className="help">sec</span>
            </div>
          </div>
        </form>

        {/* Provider/rate-limit note */}
        {pfResp?.note && (
          <div role="alert" className="help" style={{color:'var(--danger)', marginBottom:8}}>
            {String(pfResp.note)}
          </div>
        )}

        {(pfResp?.suggestions||[]).length ? (
          <div className="row">
            {pfResp.suggestions.map((sug,i)=>(
              <div key={i} className="card" style={{flex:'1 1 340px', minWidth:300}}>
                <div style={{fontWeight:600, marginBottom:6}}>{sug.symbol}</div>
                {sug.suggestion ? (
                  <>
                    <div className="help">Underlying: <b>${Number(sug.under_price).toFixed(2)}</b></div>
                    <div className="help">Idea: <b>{sug.suggestion.type}</b> {sug.suggestion.expiry} @ ${Number(sug.suggestion.strike).toFixed(2)} (premium ~ ${Number(sug.suggestion.mid_price).toFixed(2)})</div>
                    <div className="help">Breakeven: <b>${Number(sug.suggestion.breakeven).toFixed(2)}</b> | Cost (1x): <b>${Number(sug.cost_estimate).toFixed(2)}</b></div>
                    {sug.sim && <div className="help">Sim P/L — P5: <b>${sug.sim.pl_p5.toFixed(2)}</b> | Median: <b>${sug.sim.pl_p50.toFixed(2)}</b> | P95: <b>${sug.sim.pl_p95.toFixed(2)}</b> | P(profit): <b>{(sug.sim.prob_profit*100).toFixed(1)}%</b></div>}
                    <div className="help" style={{marginTop:6}}>Reasoning:</div>
                    <ul className="help" style={{marginTop:4}}>
                      {(sug.reasoning||[]).map((t,j)=><li key={j}>{t}</li>)}
                    </ul>
                    <div className="help" style={{marginTop:6}}>{sug.note}</div>
                  </>
                ) : (
                  <div className="help">{sug.note || 'No suggestion available right now.'}</div>
                )}
              </div>
            ))}
          </div>
        ) : <div className="help">{pfLoad?'Working…':'Enter portfolio JSON and click Generate.'}</div>}
      </Panel>

      <Glossary />

      <footer className="help" role="contentinfo" style={{marginTop:16}}>
        This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.
      </footer>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App/>)
