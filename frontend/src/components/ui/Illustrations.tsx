/** Hand-built hero illustrations for the "vigilance/investigation" dark
 * theme -- geometric compositions (rings, nodes, stacked documents) rather
 * than bezier-heavy figurative art, since that's the style that can be
 * built reliably and consistently without visual iteration. Every
 * illustration shares the same three-color language established
 * elsewhere in the theme: void-black, vigilance-gold, neon-green, plus a
 * slate outline -- so dropping any of them into HeroBanner looks like
 * part of one system, not eight unrelated pieces of clip art. */
import type { SVGProps } from 'react'

type Props = SVGProps<SVGSVGElement>

const GOLD = '#d9a94a'
const NEON = '#39ff8a'
const PINK = '#ff4fc3'
const BLUE = '#2ec2ff'
const SLATE = '#475569'
const SLATE_LIGHT = '#94a3b8'

function Glow({ id }: { id: string }) {
  return (
    <filter id={id} x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  )
}

/** Dashboard -- a radar sweep with a shield at its center, "always watching". */
export function RadarScanIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="radar-glow" />
        <linearGradient id="radar-sweep" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={NEON} stopOpacity="0.35" />
          <stop offset="1" stopColor={NEON} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[62, 46, 30].map((r, i) => (
        <circle key={r} cx="100" cy="80" r={r} stroke={i === 2 ? GOLD : SLATE} strokeOpacity={i === 2 ? 0.9 : 0.35} strokeWidth="1" strokeDasharray={i === 1 ? '4 4' : undefined} />
      ))}
      <path d="M100 80 L100 18 A62 62 0 0 1 153.7 111 Z" fill="url(#radar-sweep)" />
      <line x1="100" y1="80" x2="100" y2="18" stroke={NEON} strokeWidth="1.5" filter="url(#radar-glow)" />
      <circle cx="100" cy="80" r="14" fill="#0a0a0c" stroke={GOLD} strokeWidth="1.5" />
      <path d="M100 73 L106 76 L106 82 C106 87 103 90 100 91 C97 90 94 87 94 82 L94 76 Z" fill={GOLD} />
      {[
        [128, 55, NEON],
        [70, 100, NEON],
        [125, 105, PINK],
      ].map(([cx, cy, color], i) => (
        <circle key={i} cx={cx as number} cy={cy as number} r="2.4" fill={color as string} filter="url(#radar-glow)" />
      ))}
    </svg>
  )
}

/** Audits -- a case folder with a magnifying glass finding something. */
export function MagnifyingCaseIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="mag-glow" />
      </defs>
      <path d="M28 118 L28 52 C28 48 31 45 35 45 L75 45 L85 57 L165 57 C169 57 172 60 172 64 L172 118 C172 122 169 125 165 125 L35 125 C31 125 28 122 28 118 Z" fill="#0a0a0c" stroke={SLATE_LIGHT} strokeOpacity="0.5" strokeWidth="1.5" />
      <line x1="42" y1="78" x2="120" y2="78" stroke={SLATE} strokeWidth="2" strokeLinecap="round" />
      <line x1="42" y1="90" x2="100" y2="90" stroke={SLATE} strokeWidth="2" strokeLinecap="round" />
      <line x1="42" y1="102" x2="112" y2="102" stroke={SLATE} strokeWidth="2" strokeLinecap="round" />
      <circle cx="132" cy="92" r="24" fill="#0a0a0c" stroke={GOLD} strokeWidth="3" filter="url(#mag-glow)" />
      <circle cx="132" cy="92" r="16" fill="none" stroke={GOLD} strokeOpacity="0.4" strokeWidth="1" />
      <line x1="149" y1="109" x2="166" y2="126" stroke={GOLD} strokeWidth="5" strokeLinecap="round" />
      <path d="M124 92 L130 98 L142 84" stroke={NEON} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" filter="url(#mag-glow)" />
    </svg>
  )
}

/** Datasets -- a tray of data rows being scanned, one row flagged. */
export function DatasetScanIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="scan-glow" />
        <linearGradient id="scan-line" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={NEON} stopOpacity="0" />
          <stop offset="0.5" stopColor={NEON} stopOpacity="0.5" />
          <stop offset="1" stopColor={NEON} stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="34" y="34" width="132" height="96" rx="6" fill="#0a0a0c" stroke={SLATE_LIGHT} strokeOpacity="0.5" strokeWidth="1.5" />
      {[0, 1, 2, 3, 4].map((i) => {
        const y = 50 + i * 16
        const flagged = i === 2
        return (
          <g key={i}>
            <rect x="46" y={y} width="108" height="9" rx="2" fill={flagged ? undefined : '#111318'} stroke={flagged ? GOLD : SLATE} strokeWidth="1" />
            {flagged && <rect x="46" y={y} width="108" height="9" rx="2" fill={GOLD} fillOpacity="0.12" />}
            <rect x="49" y={y + 2.5} width={flagged ? 30 : 44} height="4" rx="2" fill={flagged ? GOLD : SLATE_LIGHT} fillOpacity={flagged ? 1 : 0.5} />
          </g>
        )
      })}
      <rect x="34" y="66" width="132" height="12" fill="url(#scan-line)" filter="url(#scan-glow)" />
    </svg>
  )
}

/** Weekly Revenue Closure / Delayed Cash Billing -- a stack of billing
 * documents with a verified/settled coin badge. */
export function LedgerStackIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="ledger-glow" />
      </defs>
      <g transform="rotate(-6 90 80)">
        <rect x="50" y="40" width="86" height="104" rx="4" fill="#0a0a0c" stroke={SLATE} strokeWidth="1.5" />
        <line x1="62" y1="58" x2="112" y2="58" stroke={SLATE_LIGHT} strokeOpacity="0.4" strokeWidth="2" />
        <line x1="62" y1="70" x2="100" y2="70" stroke={SLATE_LIGHT} strokeOpacity="0.4" strokeWidth="2" />
      </g>
      <g transform="rotate(4 90 80)">
        <rect x="58" y="32" width="86" height="104" rx="4" fill="#0e0f13" stroke={SLATE} strokeWidth="1.5" />
        <line x1="70" y1="50" x2="120" y2="50" stroke={SLATE_LIGHT} strokeOpacity="0.5" strokeWidth="2" />
        <line x1="70" y1="62" x2="108" y2="62" stroke={SLATE_LIGHT} strokeOpacity="0.5" strokeWidth="2" />
        <line x1="70" y1="74" x2="116" y2="74" stroke={SLATE_LIGHT} strokeOpacity="0.5" strokeWidth="2" />
      </g>
      <circle cx="140" cy="108" r="26" fill="#0a0a0c" stroke={GOLD} strokeWidth="2.5" filter="url(#ledger-glow)" />
      <text x="140" y="116" textAnchor="middle" fontSize="20" fontWeight="700" fill={GOLD} fontFamily="sans-serif">
        ₹
      </text>
      <path d="M126 108 L133 115 L154 94" stroke={NEON} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

/** Center Rankings -- a three-step podium with a trophy on top. */
export function PodiumTrophyIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="podium-glow" />
      </defs>
      <rect x="36" y="98" width="34" height="40" fill="#0e0f13" stroke={SLATE} strokeWidth="1.5" />
      <rect x="80" y="72" width="34" height="66" fill="#0a0a0c" stroke={GOLD} strokeWidth="2" filter="url(#podium-glow)" />
      <rect x="124" y="112" width="34" height="26" fill="#0e0f13" stroke={SLATE} strokeWidth="1.5" />
      <text x="53" y="122" textAnchor="middle" fontSize="14" fill={SLATE_LIGHT} fontFamily="sans-serif">2</text>
      <text x="97" y="100" textAnchor="middle" fontSize="16" fontWeight="700" fill={GOLD} fontFamily="sans-serif">1</text>
      <text x="141" y="130" textAnchor="middle" fontSize="12" fill={SLATE_LIGHT} fontFamily="sans-serif">3</text>
      <g transform="translate(97 46)">
        <path d="M-10 0 L10 0 L8 18 C8 24 -8 24 -8 18 Z" fill="none" stroke={GOLD} strokeWidth="2" />
        <path d="M-10 2 C-18 2 -18 14 -8 14" fill="none" stroke={GOLD} strokeWidth="2" />
        <path d="M10 2 C18 2 18 14 8 14" fill="none" stroke={GOLD} strokeWidth="2" />
        <circle cx="0" cy="-4" r="3" fill={NEON} />
      </g>
    </svg>
  )
}

/** Reports -- an ascending bar chart being exported/checked off. */
export function ReportBarsIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="report-glow" />
      </defs>
      <line x1="40" y1="130" x2="168" y2="130" stroke={SLATE} strokeWidth="1.5" />
      {[
        [50, 40, SLATE],
        [78, 62, BLUE],
        [106, 30, GOLD],
        [134, 78, NEON],
      ].map(([x, h, color], i) => (
        <rect key={i} x={x as number} y={130 - (h as number)} width="18" height={h as number} rx="2" fill={color as string} fillOpacity={color === SLATE ? 0.5 : 0.85} />
      ))}
      <circle cx="152" cy="46" r="18" fill="#0a0a0c" stroke={NEON} strokeWidth="2" filter="url(#report-glow)" />
      <path d="M144 46 L150 52 L161 39" stroke={NEON} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

/** Settings -- a gear with an orbiting configuration ring. */
export function GearOrbitIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="gear-glow" />
      </defs>
      <circle cx="100" cy="80" r="50" stroke={SLATE} strokeOpacity="0.35" strokeWidth="1" strokeDasharray="3 5" />
      <g filter="url(#gear-glow)">
        <circle cx="100" cy="80" r="22" fill="#0a0a0c" stroke={GOLD} strokeWidth="2.5" />
        <circle cx="100" cy="80" r="8" fill="none" stroke={GOLD} strokeWidth="2" />
        {Array.from({ length: 8 }, (_, i) => {
          const angle = (i * Math.PI) / 4
          const x1 = 100 + Math.cos(angle) * 24
          const y1 = 80 + Math.sin(angle) * 24
          const x2 = 100 + Math.cos(angle) * 31
          const y2 = 80 + Math.sin(angle) * 31
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={GOLD} strokeWidth="4" strokeLinecap="round" />
        })}
      </g>
      {[0, 120, 240].map((deg) => {
        const rad = (deg * Math.PI) / 180
        const x = 100 + Math.cos(rad) * 50
        const y = 80 + Math.sin(rad) * 50
        return <circle key={deg} cx={x} cy={y} r="4" fill={NEON} />
      })}
    </svg>
  )
}

/** Org Hierarchy / Users -- a small org chart of connected nodes. */
export function NetworkNodesIllustration(props: Props) {
  return (
    <svg viewBox="0 0 200 160" fill="none" {...props}>
      <defs>
        <Glow id="net-glow" />
      </defs>
      <line x1="100" y1="42" x2="60" y2="82" stroke={SLATE_LIGHT} strokeOpacity="0.5" strokeWidth="1.5" />
      <line x1="100" y1="42" x2="140" y2="82" stroke={SLATE_LIGHT} strokeOpacity="0.5" strokeWidth="1.5" />
      <line x1="60" y1="82" x2="38" y2="120" stroke={SLATE} strokeOpacity="0.5" strokeWidth="1.5" />
      <line x1="60" y1="82" x2="80" y2="120" stroke={SLATE} strokeOpacity="0.5" strokeWidth="1.5" />
      <line x1="140" y1="82" x2="122" y2="120" stroke={SLATE} strokeOpacity="0.5" strokeWidth="1.5" />
      <line x1="140" y1="82" x2="162" y2="120" stroke={SLATE} strokeOpacity="0.5" strokeWidth="1.5" />
      <circle cx="100" cy="42" r="12" fill="#0a0a0c" stroke={GOLD} strokeWidth="2.5" filter="url(#net-glow)" />
      {[
        [60, 82, NEON],
        [140, 82, BLUE],
      ].map(([x, y, color], i) => (
        <circle key={i} cx={x as number} cy={y as number} r="9" fill="#0e0f13" stroke={color as string} strokeWidth="2" />
      ))}
      {[
        [38, 120, SLATE_LIGHT],
        [80, 120, SLATE_LIGHT],
        [122, 120, SLATE_LIGHT],
        [162, 120, PINK],
      ].map(([x, y, color], i) => (
        <circle key={i} cx={x as number} cy={y as number} r="6" fill="#111318" stroke={color as string} strokeWidth="1.5" />
      ))}
    </svg>
  )
}
