import React, {useEffect, useMemo, useState} from 'react'
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

function Table({rows, columns, caption, onRowClick, getRowKey, getRowActive}){
  if (!rows?.length) return <div className="help">No rows.</div>
  return (
    <div className="table-wrap">
      <table role="table">
        {caption && <caption className="help" style={{textAlign:'left', marginBottom:6}}>{caption}</caption>}
        <thead><tr>{columns.map(c=><th key={c.key} scope="col">{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r,i)=>{
            const key = getRowKey ? getRowKey(r) : i
            const active = getRowActive ? getRowActive(r) : false
            return (
              <tr key={key}
                  onClick={onRowClick ? ()=>onRowClick(r) : undefined}
                  style={{cursor:onRowClick?'pointer':'default', background: active?'rgba(0,200,5,0.08)':'transparent'}}>
                {columns.map(c=><td key={c.key}>{c.render? c.render(r[c.key], r): r[c.key]}</td>)}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Card({children}){ return <div className="card" style={{flex:'1 1 380px', minWidth:320}}>{children}</div> }

function SuggestionCard({sug}){
  if (!sug) return null
  const mode = sug.mode || (sug.suggestion ? "OPTION" : "SHARES")
  const c = sug.suggestion
  return (
    <Card>
      <div style={{fontWeight:600, marginBottom:6}}>{sug.symbol}</div>
      <div className="help">Underlying price: <b>${Number(sug.under_price||0).toFixed(2)}</b></div>
      {mode === "OPTION" && c ? (
        <>
          <div className="help">Contract: <b>{c.type}</b> | Exp: <b>{c.expiry}</b> | Strike: <b>${Number(c.strike).toFixed(2)}</b></div>
          <div className="help">Premium (mid): <b>${Number(c.mid_price).toFixed(2)}</b> | Breakeven: <b>${Number(c.breakeven).toFixed(2)}</b></div>
          <div className="help">Δ: <b>{(c.delta??0).toFixed(2)}</b> | IV: <b>{(Number(c.iv||0)*100).toFixed(1)}%</b> | Chance of profit: <b>{(Number(c.chance_profit||0)*100).toFixed(1)}%</b></div>
          <div className="help">Confidence: <b>{Number(sug.confidence||0)}</b> / 100 | Cost (1x): <b>${Number(sug.cost_estimate||0).toFixed(2)}</b></div>
        </>
      ) : (
        <>
          <div className="help">Mode: <b>Buy Shares</b></div>
          {"share_probability_up_20d" in sug && (
            <div className="help">Chance of gain over ~20 trading days: <b>{(Number(sug.share_probability_up_20d)*100).toFixed(1)}%</b></div>
          )}
        </>
      )}
      {sug.explanation && <div className="help" style={{marginTop:8}}><b>Plain-English summary</b><br/>{sug.explanation}</div>}
      {sug.thought_process?.length ? (
        <>
          <div className="help" style={{marginTop:6}}><b>Thought process</b></div>
          <ul className="help" style={{marginTop:4}}>
            {sug.thought_process.map((t,i)=><li key={i}>{t}</li>)}
          </ul>
        </>
      ) : null}

      {mode === "OPTION" && c && (
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
      )}
    </Card>
  )
}

function App(){
  const [apiOk,setApiOk]=useState(null)
  useEffect(()=>{ fetch("http://localhost:8000/health").then(r=>r.json()).then(()=>setApiOk(true)).catch(()=>setApiOk(false)) },[])

  // Market Highlights
  const [sectors,setSectors]=useState(null)
  const [gainers,setGainers]=useState(null)
  const [mhNote,setMhNote]=useState(null)
  async function loadHighlights(){
    setMhNote(null)
    try{
      const r1 = await fetch("http://localhost:8000/api/screener/sectors"); const j1 = await r1.json()
      const r2 = await fetch("http://localhost:8000/api/screener/top-movers"); const j2 = await r2.json()
      setSectors(j1); setGainers(j2)
    }catch(e){ setMhNote(String(e)) }
  }
  useEffect(()=>{ loadHighlights() },[])

  const topSectors = useMemo(()=>{
    const map = sectors?.["Rank A: Real-Time Performance"] || {}
    return Object.entries(map).map(([name,p])=>({sector:name, change: parseFloat(String(p).replace('%',''))}))
      .filter(x=> isFinite(x.change)).sort((a,b)=> b.change-a.change).slice(0,6)
  },[sectors])
  const topGainers = useMemo(()=> (gainers?.top_gainers||[]).slice(0,8).map(x=>({
    ticker: x.ticker, price: x.price, change: x.change_percentage
  })), [gainers])

  const [pickedSector, setPickedSector] = useState(null)
  const [bp, setBP] = useState(3000)
  const [sectorIdeas, setSectorIdeas] = useState(null)
  const [sectorNews, setSectorNews] = useState(null)
  const [sectorNote, setSectorNote] = useState(null)
  const [sectorInsight, setSectorInsight] = useState(null)

  async function loadSectorIdeas(sectorName){
    setPickedSector(sectorName)
    setSectorIdeas(null); setSectorNews(null); setSectorNote(null); setSectorInsight(null)
    try{
      const u=new URL("http://localhost:8000/api/screener/sector-ideas")
      u.searchParams.set("sector", sectorName)
      u.searchParams.set("buying_power", String(bp))
      const r=await fetch(u); const j=await r.json()
      setSectorIdeas(j.ideas||[])
      setSectorNews(j.news||[])
      setSectorInsight(j.insight||null)
      setSectorNote(j.note||null)
    }catch(e){
      setSectorNote(String(e))
      setSectorIdeas([])
      setSectorNews([])
    }
  }

  // Quick Screener
  const [symbols,setSymbols]=useState("AAPL,MSFT,NVDA,TSLA,AMZN")
  const [scan,setScan]=useState(null)
  const [selected,setSelected]=useState(null)
  const [scanNote,setScanNote]=useState(null)
  const runScan=async()=>{
    setScanNote(null)
    try{
      const u=new URL("http://localhost:8000/api/screener/scan")
      u.searchParams.set("symbols",symbols)
      u.searchParams.set("min_volume","1000000")
      u.searchParams.set("include_history","1")
      u.searchParams.set("history_days","180")
      const r=await fetch(u); const j=await r.json()
      setScan(j); setSelected(null)
      if (j.note) setScanNote(j.note)
    }catch(e){ setScanNote(String(e)) }
  }
  useEffect(()=>{ runScan() },[])

  const scanCols = [
    {key:'symbol',label:'Symbol'},
    {key:'price',label:'Price', render:v=>Number(v).toFixed(2)},
    {key:'rsi',label:'RSI', render:v=>Number(v).toFixed(1)},
    {key:'mom_5d',label:'5d %', render:v=> isNaN(v)?'—':(Number(v)*100).toFixed(1)+'%'},
    {key:'volume',label:'Volume'},
    {key:'closes',label:'Spark', render:(v,r)=> <svg width={100} height={26}><polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={
      (r.closes||[]).map((val,i,arr)=>`${(i/(arr.length-1))*100},${26-(val/Math.max(...arr))*26}`).join(' ')
    }/></svg>},
  ]
  const scanRows = useMemo(()=> (scan?.results || []).sort((a,b)=> (b.score ?? 0) - (a.score ?? 0)), [scan?.results])

  // My Ticker
  const [mySym,setMySym]=useState("AAPL")
  const [myBP,setMyBP]=useState(5000)
  const [myIdea,setMyIdea]=useState(null)
  const [myErr,setMyErr]=useState(null)
  const [myLoad,setMyLoad]=useState(false)
  async function fetchMyIdea(){
    setMyErr(null); setMyLoad(true)
    try{
      const u=new URL("http://localhost:8000/api/options/idea")
      u.searchParams.set("symbol", mySym)
      u.searchParams.set("buying_power", String(myBP))
      const r=await fetch(u); const j=await r.json()
      setMyIdea(j)
    }catch(e){ setMyErr(String(e)) } finally { setMyLoad(false) }
  }

  return (
    <div className="container">
      <header className="header">
        <div style={{display:'flex', gap:10, alignItems:'center'}}>
          <h2 style={{margin:0}}>Quant Assistant</h2>
          <span className="badge" aria-live="polite">
            <span className={`dot ${apiOk==null?'':(apiOk?'ok':'err')}`} /> API: {apiOk==null?'checking…':(apiOk?'OK':'down')}
          </span>
        </div>
      </header>
      <div className="help" style={{marginBottom:12}}>
        This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.
      </div>

      <Panel id="highlights" title="Market Highlights" desc="Top sectors & verified top gainers. Click a sector to see 3 ideas + insight + headlines.">
        {mhNote && <div role="alert" className="help" style={{color:'var(--danger)'}}>{mhNote}</div>}
        <div className="row">
          <div style={{flex:'1 1 420px', minWidth:320}}>
            <div className="help" style={{marginBottom:6, display:'flex', gap:10, alignItems:'center'}}>
              <span>Sector performance (click to drill down)</span>
              <button className="button" onClick={loadHighlights}>Reload</button>
            </div>
            <SectorBar rows={topSectors} onBarClick={(row)=>{ setPickedSector(row.sector); loadSectorIdeas(row.sector) }}/>
          </div>
          <div style={{flex:'1 1 420px', minWidth:320}}>
            <div className="help" style={{marginBottom:6}}>Top gainers (real tickers)</div>
            <GainersBar rows={topGainers}/>
          </div>
        </div>

        {pickedSector && (
          <div className="panel" style={{marginTop:12}}>
            <h3 style={{marginTop:0}}>{pickedSector} — 3 ideas</h3>
            {sectorInsight && <div className="help" style={{marginBottom:6}}><b>Insight:</b> {sectorInsight}</div>}
            {sectorNote && <div role="alert" className="help" style={{color:'var(--danger)'}}>{sectorNote}</div>}
            {(sectorIdeas||[]).length ? (
              <div className="row">
                {sectorIdeas.map((s,i)=><SuggestionCard key={i} sug={s} />)}
              </div>
            ) : <div className="help">No ideas yet.</div>}

            <h4 style={{marginTop:12, marginBottom:6}}>Why this sector is moving (headlines)</h4>
            {(sectorNews||[]).length ? (
              <ul className="help" style={{marginTop:0}}>
                {sectorNews.map((n,i)=>
                  <li key={i}>
                    <a href={n.url || '#'} target="_blank" rel="noreferrer">{n.title || 'headline'}</a>
                    {n.publisher ? <> — <span>{n.publisher}</span></> : null}
                    {n.symbol ? <> <span style={{opacity:0.7}}>({n.symbol})</span></> : null}
                  </li>
                )}
              </ul>
            ) : <div className="help">No recent headlines found.</div>}
          </div>
        )}
      </Panel>

      <Panel id="screener" title="Quick Screener" desc="Type tickers, run, then click a row to see details.">
        <form className="row" onSubmit={(e)=>{e.preventDefault();runScan()}}>
          <div className="input" style={{flex:'1 1 520px'}}>
            <label htmlFor="tickers">Tickers (comma‑separated)</label>
            <input id="tickers" value={symbols} onChange={e=>setSymbols(e.target.value)} />
          </div>
          <div className="input">
            <button className="button" type="submit">Scan</button>
          </div>
        </form>
        {scanNote && <div className="help" role="alert" style={{color:'var(--danger)'}}>{scanNote}</div>}
        <Table
          rows={scanRows}
          columns={scanCols}
          caption="Ranked by composite score (desc)"
          onRowClick={setSelected}
          getRowKey={(r)=>r.symbol}
          getRowActive={(r)=> selected?.symbol===r.symbol}
        />
        <div style={{marginTop:12}}>
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
                  <div className="help">EMA(12)/(26): <b>{Number(selected.ema_short).toFixed(2)}</b> / <b>{Number(selected.ema_long).toFixed(2)}</b></div>
                  <div className="help">5‑day return: <b>{isNaN(selected.mom_5d)?'—':(Number(selected.mom_5d)*100).toFixed(1)+'%'}</b></div>
                  <div className="help">Volume: <b>{Number(selected.volume).toLocaleString()}</b></div>
                </div>
              </div>
            </div>
          ) : <div className="help">Click a screener row to see details here.</div>}
        </div>
      </Panel>

      <Panel id="myticker" title="Options — My Ticker (single scan)" desc="We pick one contract using liquidity, Δ≈0.30, DTE 21–45 (fallbacks 14–60, 30–90), affordability, and trend alignment.">
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
            <button className="button" type="submit">{myLoad? 'Working…' : 'Get idea'}</button>
          </div>
        </form>
        {myErr && <div role="alert" className="help" style={{color:'var(--danger)'}}>{String(myErr)}</div>}
        {myIdea?.note && <div className="help" style={{color:'var(--danger)'}}>{String(myIdea.note)}</div>}
        {myIdea?.picked_window && <div className="help">Used DTE window: <b>{myIdea.picked_window[0]}–{myIdea.picked_window[1]}</b> days</div>}
        {myIdea?.suggestion ? <SuggestionCard sug={myIdea}/> : <div className="help" style={{marginTop:8}}>No suggestion yet.</div>}
      </Panel>

      <Glossary />
      <footer className="help" role="contentinfo" style={{marginTop:16}}>
        This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.
      </footer>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App/>)
