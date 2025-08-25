import React from 'react'

const TERMS = [
  { term: 'ITM / OTM', def: 'In/Out of the Money. Call is ITM if stock > strike; Put is ITM if stock < strike.' },
  { term: 'Strike', def: 'Price where the option can be exercised.' },
  { term: 'Premium', def: 'Price of the option contract.' },
  { term: 'Breakeven', def: 'Price at expiry where profit is $0 (Call: K+premium; Put: K−premium).' },
  { term: 'Delta (Δ)', def: 'How much the option price moves when the stock moves $1 (approx).' },
  { term: 'IV', def: 'Implied Volatility – the market’s estimate of future movement.' },
  { term: 'Monte Carlo', def: 'Many simulated price paths to estimate possible outcomes.' }
]

export default function Glossary(){
  return (
    <div className="panel">
      <h3>Glossary</h3>
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
