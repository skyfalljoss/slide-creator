import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'

type IconProps = { className?: string }

function LogoMark({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="sf-logo" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop stopColor="#38bdf8" />
          <stop offset="0.5" stopColor="#6366f1" />
          <stop offset="1" stopColor="#a855f7" />
        </linearGradient>
      </defs>
      <path
        d="M13.5 2 4 13.2c-.5.6-.1 1.5.7 1.5H11l-1.5 7.3c-.2.9 1 1.4 1.6.7L20 11.5c.5-.6.1-1.5-.7-1.5H13l1.6-7.2c.2-.9-1-1.4-1.6-.8Z"
        fill="url(#sf-logo)"
      />
    </svg>
  )
}

function IconNewDeck({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  )
}

function IconMyDecks({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  )
}

function IconTemplates({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  )
}

function IconAssets({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M12 3l1.9 4.7L19 9.5l-4 3.4 1.2 5.3L12 15.8 7.8 18.2 9 12.9l-4-3.4 5.1-1.8z" />
    </svg>
  )
}

function IconSettings({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}

interface NavItem {
  label: string
  to: string
  icon: (props: IconProps) => React.JSX.Element
}

const NAV_ITEMS: NavItem[] = [
  { label: 'New Deck', to: '/create', icon: IconNewDeck },
  { label: 'My Decks', to: '/my-decks', icon: IconMyDecks },
  { label: 'Templates', to: '/templates', icon: IconTemplates },
  { label: 'AI Assets', to: '/assets', icon: IconAssets },
  { label: 'Settings', to: '/settings', icon: IconSettings },
]

function navClasses(isActive: boolean) {
  return cn(
    'group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all',
    isActive
      ? 'tile-active text-white'
      : 'text-slate-400 hover:text-slate-100 hover:bg-white/5',
  )
}

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-white/10 bg-space-950/70 px-4 py-6 backdrop-blur-xl lg:flex">
      <div className="flex items-center gap-2.5 px-2">
        <LogoMark className="h-8 w-8 drop-shadow-[0_0_12px_rgba(99,102,241,0.6)]" />
        <span className="font-display text-xl font-bold tracking-tight text-white">SlideForge</span>
      </div>

      <nav className="mt-10 flex flex-1 flex-col gap-1.5" aria-label="Primary">
        {NAV_ITEMS.map(({ label, to, icon: Icon }) => (
          <NavLink key={label} to={to} end className={({ isActive }) => navClasses(isActive)}>
            <Icon className="h-5 w-5 shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <NavLink to="/settings" className={({ isActive }) => navClasses(isActive)}>
        <IconSettings className="h-5 w-5 shrink-0" />
        <span>Settings</span>
      </NavLink>
    </aside>
  )
}
