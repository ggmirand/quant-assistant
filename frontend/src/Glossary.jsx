import React from 'react'

const TERMS = [
  { term: 'ITM / OTM', def: 'In the Money / Out of the Money. A call is ITM if stock price > strike. A put is ITM if stock price < strike.' },
  { term: 'Strike', def: 'The price where the option can be exercised.' },
  { term: 'Premium', def: 'What you pay for the option (the option’s price).' },
  { term: 'Breakeven', def: 'Stock price at expiry where your profit is $0. Call: strike + premium. Put: strike − premium.' },
  { term: 'Delta (Δ)', def: 'How much the option price moves if the stock moves $1 (approx).' },
  { term: 'IV', def: 'Implied Volatility – the market’s estimate of how much the stock could move.' },
  { term: 'RSI', def: 'Relative Strength Index – a momentum indicator; near 70 is “hot,” near 30 is “cool.”' },
  { term: 'EMA', def: 'Exponential Moving Average – smoothed average price; EMA(12) crossing above EMA(26) can suggest uptrend.' },
  { term: 'Monte Carlo', def: 'Many simulated price paths to see a range of possible future outcomes.' }
]

export default function Glossary(){
  return (
    <div className="panel">
      <h3>Glossary</h3>
      <div className="help" style={{marginBottom:8}}>Quick definitions in plain English.</div>
      <ul style={{listStyle:'none', padding:0, margin:0}}>
        {TERMS.map((t,i)=>(
          <li key={i} style={{padding:'8px 0', borderBottom:'1px solid var(--border)'}}>
            <div style={{fontWeight:600}}>{t.term}</div>
            <div className="help">{t.def}</div>
          </li>
        ))}
      </ul>
    </div>
  )
}
