import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-space-950 text-slate-200">
      {/* Ambient space backdrop: deep radial glows + drifting constellation */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0">
        <div
          className="absolute inset-0"
          style={{
            background:
              'radial-gradient(1200px 600px at 78% -5%, rgba(59,130,246,0.18), transparent 60%), radial-gradient(900px 500px at 12% 8%, rgba(139,92,246,0.14), transparent 55%), radial-gradient(700px 600px at 60% 110%, rgba(99,102,241,0.16), transparent 60%)',
          }}
        />
        <div
          className="absolute inset-0 animate-drift opacity-60"
          style={{
            backgroundImage:
              'radial-gradient(1px 1px at 20px 30px, rgba(255,255,255,0.45), transparent), radial-gradient(1px 1px at 120px 80px, rgba(180,200,255,0.4), transparent), radial-gradient(1.5px 1.5px at 220px 160px, rgba(255,255,255,0.35), transparent), radial-gradient(1px 1px at 320px 60px, rgba(150,180,255,0.4), transparent)',
            backgroundSize: '400px 240px, 360px 220px',
          }}
        />
      </div>

      <Sidebar />

      <main className="relative z-10 px-4 py-10 sm:px-8 lg:pl-72 lg:pr-10">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
