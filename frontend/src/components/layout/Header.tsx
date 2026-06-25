import { Button } from '@/components/ui/Button'

interface HeaderProps {
  onLogout?: () => void
  userName?: string
}

export function Header({ onLogout, userName }: HeaderProps) {
  return (
    <header className="sticky top-0 z-40 bg-white/80 backdrop-blur border-b border-slate-200">
      <div className="flex items-center justify-between h-16 px-6 lg:px-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-citi-blue flex items-center justify-center">
            <span className="text-white font-bold text-xs">c</span>
          </div>
          <div>
            <h1 className="text-[17px] font-semibold leading-tight">SlideForge</h1>
            <p className="text-[11px] text-slate-500">AI Presentation Generator</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {userName && <span className="text-sm text-slate-600">{userName}</span>}
          {onLogout && (
            <Button variant="ghost" size="sm" onClick={onLogout}>
              Logout
            </Button>
          )}
        </div>
      </div>
    </header>
  )
}
