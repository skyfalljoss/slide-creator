import { cn } from '@/lib/utils'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'glow'
  size?: 'sm' | 'md' | 'lg'
}

export function Button({ className, variant = 'default', size = 'md', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400/60 disabled:pointer-events-none disabled:opacity-50',
        variant === 'default' && 'bg-citi-blue text-white hover:bg-[#045a92]',
        variant === 'outline' && 'border border-slate-300 bg-white hover:bg-slate-50',
        variant === 'ghost' && 'hover:bg-slate-100',
        variant === 'glow' && 'btn-glow rounded-xl font-semibold tracking-wide',
        size === 'sm' && 'h-8 px-3 text-xs',
        size === 'md' && 'h-10 px-4 text-sm',
        size === 'lg' && 'h-12 px-6 text-base',
        className,
      )}
      {...props}
    />
  )
}
