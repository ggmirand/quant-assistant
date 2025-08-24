import React from 'react'
import {
  Chart as ChartJS, LineController, LineElement,
  PointElement, CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'
import { Line } from 'react-chartjs-2'

ChartJS.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend)

/**
 * PayoffChart
 * Draws profit/loss at expiry for a single LONG option (call or put).
 * Inputs:
 *  - s0: current underlying price (for center line)
 *  - type: 'CALL' | 'PUT'
 *  - strike: number
 *  - premium: number (mid)
 *  - pctRange: percent left/right around s0 (default ±40%)
 */
export default function PayoffChart({ s0, type='CALL', strike, premium, pctRange=0.4 }) {
  if (!isFinite(s0) || !isFinite(strike) || !isFinite(premium)) {
    return <div className="help">No data for payoff chart.</div>
  }
  const N = 80
  const lo = Math.max(0.01, s0 * (1 - pctRange))
  const hi = s0 * (1 + pctRange)
  const xs = Array.from({length: N}, (_,i)=> lo + (i/(N-1))*(hi-lo))
  const pl = xs.map(S => {
    if (String(type).toUpperCase() === 'CALL') {
      return Math.max(0, S - strike) - premium
    } else {
      return Math.max(0, strike - S) - premium
    }
  })

  const labels = xs.map(v => v.toFixed(0))
  const data = {
    labels,
    datasets: [{
      label: 'P/L at expiry',
      data: pl,
      borderColor: '#00c805',
      backgroundColor: 'rgba(0,200,5,0.2)',
      tension: 0.2,
      pointRadius: 0
    }]
  }
  const options = {
    responsive: true,
    plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#8aa1b2', maxTicksLimit: 6 } },
      y: { grid: { color:'rgba(138,161,178,0.2)' }, ticks: { color:'#8aa1b2', callback: v => `$${Number(v).toFixed(0)}` } }
    }
  }
  return <Line data={data} options={options}/>
}
