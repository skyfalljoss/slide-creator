import { Outlet } from 'react-router-dom'
import { Header } from './Header'

export function Layout() {
  return (
    <div className="min-h-screen bg-citi-gray">
      <Header userName="Demo User" />
      <main className="max-w-6xl mx-auto px-4 py-8 lg:px-8">
        <Outlet />
      </main>
    </div>
  )
}
