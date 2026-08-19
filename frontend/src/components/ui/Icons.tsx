/** A small, self-drawn icon set for the "vigilance/investigation" theme --
 * no external icon library dependency. Every icon is a plain 24x24 stroke
 * glyph (currentColor), sized via className like any other element. */
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function base(children: React.ReactNode, props: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  )
}

export function ShieldIcon(props: IconProps) {
  return base(
    <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />,
    props,
  )
}

export function SearchIcon(props: IconProps) {
  return base(
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="M20 20l-4.7-4.7" />
    </>,
    props,
  )
}

export function FolderIcon(props: IconProps) {
  return base(
    <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l2 2.5h9A1.5 1.5 0 0 1 21 9v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18Z" />,
    props,
  )
}

export function ReceiptIcon(props: IconProps) {
  return base(
    <>
      <path d="M6 3h12v18l-2.5-1.5L13 21l-2.5-1.5L8 21l-2-1.5V3Z" />
      <path d="M9 8h6M9 12h6M9 16h3" />
    </>,
    props,
  )
}

export function CalendarClockIcon(props: IconProps) {
  return base(
    <>
      <rect x="3" y="4.5" width="18" height="16" rx="2" />
      <path d="M3 9.5h18M8 2.5v4M16 2.5v4" />
      <circle cx="15.5" cy="15" r="3.2" />
      <path d="M15.5 13.4V15l1.1.9" />
    </>,
    props,
  )
}

export function ChartIcon(props: IconProps) {
  return base(
    <>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </>,
    props,
  )
}

export function TrophyIcon(props: IconProps) {
  return base(
    <>
      <path d="M7 4h10v5a5 5 0 0 1-10 0V4Z" />
      <path d="M7 6H4.5A1.5 1.5 0 0 0 3 7.5C3 9.5 4.5 11 7 11M17 6h2.5A1.5 1.5 0 0 1 21 7.5C21 9.5 19.5 11 17 11" />
      <path d="M12 14v3M9 20.5h6M9.5 20.5c0-1.8.5-3 2.5-3s2.5 1.2 2.5 3" />
    </>,
    props,
  )
}

export function CogIcon(props: IconProps) {
  return base(
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.2M12 18.8V21M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M3 12h2.2M18.8 12H21M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6" />
    </>,
    props,
  )
}

export function BuildingIcon(props: IconProps) {
  return base(
    <>
      <rect x="4" y="3" width="16" height="18" rx="1" />
      <path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 16h1M14 16h1" />
    </>,
    props,
  )
}

export function UsersIcon(props: IconProps) {
  return base(
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 20c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
      <circle cx="17.5" cy="9" r="2.3" />
      <path d="M15.5 12.3c2.4.3 4 1.9 4 4.2" />
    </>,
    props,
  )
}

export function HomeIcon(props: IconProps) {
  return base(
    <>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6 10v9.5a1 1 0 0 0 1 1h3v-6h4v6h3a1 1 0 0 0 1-1V10" />
    </>,
    props,
  )
}

export function LogoutIcon(props: IconProps) {
  return base(
    <>
      <path d="M9 4H5.5A1.5 1.5 0 0 0 4 5.5v13A1.5 1.5 0 0 0 5.5 20H9" />
      <path d="M13 16l4-4-4-4M17 12H8" />
    </>,
    props,
  )
}

export function EyeIcon(props: IconProps) {
  return base(
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.6" />
    </>,
    props,
  )
}

/** The same open-eye outline, plus a diagonal strike-through -- "hidden",
 * for the password show/hide toggle's off state. */
export function EyeOffIcon(props: IconProps) {
  return base(
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.6" />
      <path d="M4 4 20 20" />
    </>,
    props,
  )
}

export function ChevronDownIcon(props: IconProps) {
  return base(<path d="M5 8.5 12 15.5 19 8.5" />, props)
}

export function CheckIcon(props: IconProps) {
  return base(<path d="M4.5 12.5 9.5 17.5 19.5 6.5" />, props)
}
