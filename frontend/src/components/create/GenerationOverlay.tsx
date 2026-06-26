import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

const STEPS = [
  'Analyzing your brief',
  'Structuring the narrative',
  'Generating slide content',
  'Designing layouts & visuals',
  'Polishing the final deck',
] as const

interface GenerationOverlayProps {
  active: boolean
  /** When true, we are still uploading the data file before generation. */
  uploading?: boolean
}

/**
 * Full-screen loading phase shown while a deck is being generated.
 * Cycles through human-readable AI phases with a pulsing orb and an
 * animated progress bar so the user can see work happening in the background.
 */
export function GenerationOverlay({ active, uploading = false }: GenerationOverlayProps) {
  const [step, setStep] = useState(0)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    if (!active) return

    const stepTimer = setInterval(() => {
      setStep((s) => Math.min(s + 1, STEPS.length - 1))
    }, 1700)

    // Ease toward 95% so the bar feels alive but never "completes" early.
    const progressTimer = setInterval(() => {
      setProgress((p) => (p >= 95 ? 95 : p + Math.max(0.6, (95 - p) * 0.08)))
    }, 220)

    return () => {
      clearInterval(stepTimer)
      clearInterval(progressTimer)
    }
  }, [active])

  if (!active) return null

  const headline = uploading ? 'Reading your data file' : 'Forging your deck'

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-space-950/80 px-4 backdrop-blur-xl"
    >
      <div className="glass-card w-full max-w-md p-8 text-center">
        {/* Pulsing AI orb with an orbiting ring */}
        <div className="relative mx-auto h-24 w-24">
          <span className="absolute inset-0 animate-orbit rounded-full border-2 border-transparent border-t-indigo-400 border-r-violet-400" />
          <span className="absolute inset-2 rounded-full bg-gradient-to-br from-sky-400 via-indigo-500 to-violet-500 animate-pulse-glow" />
          <span className="absolute inset-0 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="h-9 w-9 drop-shadow" aria-hidden="true">
              <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z" />
              <path d="M18.5 14l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
            </svg>
          </span>
        </div>

        <h2 className="mt-6 font-display text-2xl font-bold text-white">{headline}</h2>
        <p className="mt-1 min-h-[1.5rem] text-sm text-indigo-300 transition-all">
          {uploading ? 'Parsing rows and columns…' : `${STEPS[step]}…`}
        </p>

        {/* Progress bar with a moving shimmer */}
        <div className="mt-6 h-2 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className="relative h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-sky-400 transition-[width] duration-300 ease-out"
            style={{ width: `${Math.round(progress)}%` }}
          >
            <span className="absolute inset-0 animate-shimmer bg-gradient-to-r from-transparent via-white/40 to-transparent" />
          </div>
        </div>
        <p className="mt-2 text-right text-xs text-slate-500">{Math.round(progress)}%</p>

        {/* Step checklist */}
        {!uploading && (
          <ul className="mt-5 space-y-2 text-left">
            {STEPS.map((label, i) => {
              const done = i < step
              const current = i === step
              return (
                <li key={label} className="flex items-center gap-3 text-sm">
                  <span
                    className={cn(
                      'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px]',
                      done && 'border-emerald-400/60 bg-emerald-400/15 text-emerald-300',
                      current && 'border-indigo-400/70 bg-indigo-400/15 text-indigo-200',
                      !done && !current && 'border-white/15 text-transparent',
                    )}
                  >
                    {done ? '✓' : current ? '•' : '•'}
                  </span>
                  <span
                    className={cn(
                      done && 'text-slate-300',
                      current && 'text-white',
                      !done && !current && 'text-slate-500',
                    )}
                  >
                    {label}
                  </span>
                </li>
              )
            })}
          </ul>
        )}

        <p className="mt-6 text-xs text-slate-500">This usually takes just a few seconds.</p>
      </div>
    </div>
  )
}
