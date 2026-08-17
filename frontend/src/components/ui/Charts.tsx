import { Bar, BarChart, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

/** Real, animated charts (recharts) for the dark theme -- replaces the
 * hand-rolled CSS bar-lists that used to stand in for charts. Bars grow in
 * on mount/update (recharts' own animation, left at its default), colored
 * from the same gold/green/pink/blue accent language used everywhere else
 * in the theme rather than recharts' stock blue. */

const PALETTE = ['#d9a94a', '#12e673', '#2ec2ff', '#ff4fc3', '#9c7422', '#7cffb8']

interface BarDatum {
  label: string
  value: number
}

/** Horizontal bar chart -- one bar per label, colored around the palette.
 * Used for status/severity breakdowns and center-ranking leaderboards. */
export function HorizontalBarChart({
  data,
  height,
  valueFormatter,
}: {
  data: BarDatum[]
  height?: number
  valueFormatter?: (v: number) => string
}) {
  if (data.length === 0) return null
  const rowHeight = 34
  return (
    <ResponsiveContainer width="100%" height={height ?? Math.max(120, data.length * rowHeight)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }} barCategoryGap={10}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          width={140}
          tick={{ fill: '#94a3b8', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={{ fill: 'rgba(255,255,255,0.03)' }}
          contentStyle={{ background: '#050506', border: '1px solid rgba(217,169,74,0.3)', borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: '#e2e8f0' }}
          itemStyle={{ color: '#d9a94a' }}
          formatter={(value) => [valueFormatter && typeof value === 'number' ? valueFormatter(value) : String(value ?? ''), 'Count']}
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive animationDuration={700}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Converts the app's common `Record<string, number>` breakdown shape
 * (e.g. audits-by-status) into the {label, value}[] shape charts expect. */
export function recordToBarData(record: Record<string, number>): BarDatum[] {
  return Object.entries(record).map(([label, value]) => ({ label, value }))
}

/** Donut/pie chart -- used for cluster-wise / zone-wise non-compliant
 * center share and similar proportional breakdowns. */
export function PieChartWidget({ data, height }: { data: BarDatum[]; height?: number }) {
  if (data.length === 0) return null
  return (
    <ResponsiveContainer width="100%" height={height ?? 260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          innerRadius="45%"
          outerRadius="80%"
          paddingAngle={2}
          isAnimationActive
          animationDuration={700}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} stroke="#050506" />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: '#050506', border: '1px solid rgba(217,169,74,0.3)', borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: '#e2e8f0' }}
          itemStyle={{ color: '#d9a94a' }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
      </PieChart>
    </ResponsiveContainer>
  )
}
