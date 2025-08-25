import React, {useRef} from 'react'
import {
  Chart as ChartJS, BarElement, BarController,
  CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'
import { Bar, getElementAtEvent } from 'react-chartjs-2'

ChartJS.register(BarElement, BarController, CategoryScale, LinearScale, Tooltip, Legend)

const baseOpts = {
  responsive: true,
  plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
  scales: {
    x: { grid: { display:false }, ticks: { color: '#94a3b8' } },
    y: { grid: { color: 'rgba(148,163,184,0.2)' }, ticks: { color: '#94a3b8' } }
  }
}

export function SectorBar({rows = [], onBarClick}) {
  const labels = rows.map(r => r.sector)
  const data = {
    labels,
    datasets: [{
      label: '% Change',
      data: rows.map(r => r.change),
      borderColor: '#00c805',
      backgroundColor: 'rgba(0,200,5,0.35)'
    }]
  }
  const ref = useRef(null)
  const handleClick = (evt) => {
    if (!onBarClick || !ref.current) return
    const els = getElementAtEvent(ref.current, evt)
    if (!els || !els.length) return
    const idx = els[0].index
    const row = rows[idx]
    if (row) onBarClick(row)
  }
  return (
    <Bar
      ref={ref}
      data={data}
      onClick={handleClick}
      options={{
        ...baseOpts,
        plugins: {
          ...baseOpts.plugins,
          tooltip: { callbacks: { label: c => `${(c.parsed.y || 0).toFixed(2)}%` } }
        }
      }}
    />
  )
}

export function GainersBar({rows = []}) {
  const labels = rows.map(r => r.ticker)
  const nums = rows.map(r => parseFloat(String(r.change || '').replace('%', '')) || 0)
  const data = {
    labels,
    datasets: [{
      label: '% Change',
      data: nums,
      borderColor: '#60a5fa',
      backgroundColor: 'rgba(96,165,250,0.35)'
    }]
  }
  return (
    <Bar
      data={data}
      options={{
        ...baseOpts,
        plugins: {
          ...baseOpts.plugins,
          tooltip: { callbacks: { label: c => `${(c.parsed.y || 0).toFixed(2)}%` } }
        }
      }}
    />
  )
}

export function Histogram({values = [], bins = 20, color = '#eab308', title = 'Histogram'}) {
  if (!values?.length) return <div className="help">No data</div>
  const min = Math.min(...values), max = Math.max(...values)
  const width = (max - min) || 1
  const step = width / bins
  const edges = Array.from({length: bins}, (_, i) => min + i * step)
  const counts = Array.from({length: bins}, () => 0)

  for (const v of values) {
    let idx = Math.floor((v - min) / step)
    if (idx >= bins) idx = bins - 1
    if (idx < 0) idx = 0
    counts[idx]++
  }

  const labels = edges.map((e, i) => (i === 0 ? e.toFixed(2) : ''))
  const data = {
    labels,
    datasets: [{
      label: title,
      data: counts,
      borderColor: color,
      backgroundColor: `${color}55`
    }]
  }
  return (
    <Bar
      data={data}
      options={{
        ...baseOpts,
        plugins: { ...baseOpts.plugins, legend: { display: false } }
      }}
    />
  )
}
