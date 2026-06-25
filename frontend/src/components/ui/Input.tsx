import { cn } from '@/lib/utils'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export function Input({ className, label, error, id, ...props }: InputProps) {
  return (
    <div className="space-y-1">
      {label && <label htmlFor={id} className="text-sm font-medium text-slate-700">{label}</label>}
      <input
        id={id}
        className={cn(
          'flex h-10 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-citi-blue/50 focus:border-citi-blue disabled:cursor-not-allowed disabled:opacity-50',
          error && 'border-citi-red focus:ring-citi-red/50',
          className,
        )}
        {...props}
      />
      {error && <p className="text-xs text-citi-red">{error}</p>}
    </div>
  )
}
