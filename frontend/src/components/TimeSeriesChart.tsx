import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export interface Series {
  key: string
  label: string
  color: string
}

interface Props {
  data: Record<string, number | string | null>[]
  series: Series[]
  yFormatter?: (v: number) => string
  height?: number
}

export default function TimeSeriesChart({ data, series, yFormatter, height = 220 }: Props) {
  if (data.length === 0) return <p className="muted">Sin datos en este rango todavía.</p>
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#2a3140" strokeDasharray="3 3" />
        <XAxis dataKey="t" tick={{ fill: '#8b95a7', fontSize: 11 }} minTickGap={40} />
        <YAxis tick={{ fill: '#8b95a7', fontSize: 11 }} tickFormatter={yFormatter} width={72} />
        <Tooltip
          contentStyle={{ background: '#1a1f2b', border: '1px solid #2a3140' }}
          formatter={value => (typeof value === 'number' && yFormatter ? yFormatter(value) : value)}
        />
        <Legend />
        {series.map(s => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
