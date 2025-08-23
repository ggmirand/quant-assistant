import React from 'react'
import {
  Chart as ChartJS, LineController, LineElement, PointElement,
  BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'
import { Chart } from 'react-chartjs-2'

ChartJS.register(LineController, LineElement, PointElement, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

export default function PriceVolume({closes=[], volumes=[]}) {
  if (!closes?.length) return <div className="help">No data</div>
  const labels = Array.from({length: closes.length}, (_,i)=> `-${closes.length-1-i}`)
  const maxVol = Math.max(...(volumes||[]), 1)
  const data = {
    labels,
    datasets: [
      {
        type: 'line',
        label: 'Price',
        data: closes,
        borderColor: '#00c805',
        backgroundColor: 'rgba(0,200,5,0.2)',
        tension: 0.25, pointRadius: 0, yAxisID: 'y'
      },
      {
        type: 'bar',
        label: 'Volume',
        data: (volumes||[]).map(v => v / maxVol * 100),
        backgroundColor: 'rgba(100,130,200,0.25)',
        borderColor: 'rgba(100,130,200,0.5)',
        yAxisID: 'y1'
      }
    ]
  }
  const options = {
    responsive: true,
    plugins: { legend: { display: false }, tooltip: { mode:'index', intersect:false } },
    scales: {
      x: { grid: { display:false }, ticks: { color:'#8aa1b2', maxTicksLimit: 6 } },
      y: { position:'left', grid: { color:'rgba(138,161,178,0.2)' }, ticks:{ color:'#8aa1b2' } },
      y1:{ position:'right', grid:{ display:false }, ticks:{ color:'#8aa1b2', callback:v=> v+'%' }, suggestedMax: 100 }
    }
  }
  return <Chart type='bar' data={data} options={options}/>
}
