import type { SlideBlock, SlideBlockItem } from '@/types'

const ICON_CLASSES: [string[], string][] = [
  [['speed', 'velocity', 'fast', 'performance', 'agile', 'efficiency', 'accelerate'], 'fa-bolt'],
  [['security', 'secure', 'compliance', 'trust', 'protect', 'risk', 'privacy', 'governance'], 'fa-shield-halved'],
  [['growth', 'grow', 'increase', 'expand', 'revenue', 'value', 'roi', 'return', 'scale'], 'fa-arrow-trend-up'],
  [['global', 'network', 'reach', 'connect', 'integration', 'ecosystem', 'api', 'market', 'worldwide'], 'fa-globe'],
  [['process', 'system', 'automation', 'operations', 'workflow', 'engine', 'infrastructure'], 'fa-gears'],
  [['quality', 'excellence', 'premium', 'award', 'leader', 'best', 'rating'], 'fa-star'],
  [['innovation', 'idea', 'insight', 'vision', 'future', 'strategy', 'opportunity'], 'fa-lightbulb'],
  [['client', 'customer', 'people', 'team', 'partner', 'relationship', 'service', 'audience'], 'fa-users'],
  [['chart', 'financial', 'metrics', 'analysis', 'results', 'data', 'analytics'], 'fa-chart-line'],
  [['cloud', 'platform', 'technology', 'digital', 'storage', 'database'], 'fa-database'],
  [['next', 'step', 'action', 'timeline', 'plan', 'roadmap', 'phase', 'deliver'], 'fa-arrow-right'],
  [['goal', 'objective', 'target', 'focus', 'mission'], 'fa-bullseye'],
]

function faClass(keyword?: string): string {
  const text = (keyword || '').toLowerCase()
  for (const [words, cls] of ICON_CLASSES) {
    if (words.some((w) => text.includes(w))) return cls
  }
  return 'fa-circle-check'
}

function normItems(items?: Array<string | SlideBlockItem>): SlideBlockItem[] {
  return (items ?? []).map((it) => (typeof it === 'string' ? { body: it } : it))
}

function Chip({ icon }: { icon?: string }) {
  return (
    <span className="mb-2 inline-flex h-8 w-8 items-center justify-center rounded-md bg-rose-500/15 text-rose-300">
      <i className={`fa-solid ${faClass(icon)} text-sm`} aria-hidden="true" />
    </span>
  )
}

function BlockView({ block }: { block: SlideBlock }) {
  const type = (block.type || '').toLowerCase()

  if (type === 'stat') {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center">
        <div className="text-5xl font-bold tracking-tight text-rose-400">{block.value || block.number}</div>
        {(block.label || block.caption) && (
          <div className="mt-2 text-sm font-medium text-slate-200">{block.label || block.caption}</div>
        )}
      </div>
    )
  }

  if (type === 'quote') {
    return (
      <div className="flex h-full items-center">
        <div className="border-l-4 border-citi-red pl-4">
          <p className="text-lg font-semibold leading-snug text-slate-100">&ldquo;{block.text || block.quote}&rdquo;</p>
          {block.author && <p className="mt-2 text-xs uppercase tracking-wide text-slate-400">{block.author}</p>}
        </div>
      </div>
    )
  }

  if (type === 'table' || type === 'comparison') {
    const headers = block.headers ?? []
    const rows = block.rows ?? []
    return (
      <table className="w-full border-collapse text-left text-xs">
        {headers.length > 0 && (
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={i} className="border-b-2 border-white/20 px-2 py-1.5 font-semibold text-slate-200">{h}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              {r.map((c, ci) => (
                <td key={ci} className={`border-b border-white/10 px-2 py-1.5 ${ci === 0 ? 'font-medium text-slate-200' : 'text-slate-400'}`}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  if (type === 'process' || type === 'steps' || type === 'timeline') {
    const steps = normItems(block.steps ?? block.items)
    return (
      <div className="grid h-full gap-3" style={{ gridTemplateColumns: `repeat(${Math.max(steps.length, 1)}, minmax(0, 1fr))` }}>
        {steps.map((s, i) => (
          <div key={i} className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-citi-red text-xs font-bold text-white">{i + 1}</span>
            {s.title && <div className="mt-2 text-sm font-semibold text-slate-100">{s.title}</div>}
            {(s.body || s.text) && <div className="mt-1 text-xs text-slate-400">{s.body || s.text}</div>}
          </div>
        ))}
      </div>
    )
  }

  if (type === 'cards' || type === 'card_grid' || type === 'grid' || type === 'columns') {
    const items = normItems(block.items ?? block.cards)
    const cols = block.columns || (items.length >= 3 ? 3 : Math.max(items.length, 1))
    return (
      <div className="grid h-full gap-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {items.map((it, i) => (
          <div key={i} className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
            <Chip icon={it.icon || it.title} />
            {it.title && <div className="text-sm font-semibold text-slate-100">{it.title}</div>}
            {(it.body || it.text) && <div className="mt-1 text-xs text-slate-400">{it.body || it.text}</div>}
          </div>
        ))}
      </div>
    )
  }

  // bullets / fallback
  const items = normItems(block.items)
  return (
    <ul className="space-y-2">
      {items.map((it, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-citi-red" />
          <span>{it.title || it.body || it.text}</span>
        </li>
      ))}
    </ul>
  )
}

export function SlideBlocks({ blocks }: { blocks: SlideBlock[] }) {
  return (
    <div className="mt-5 flex flex-1 flex-col gap-3 overflow-hidden">
      {blocks.map((b, i) => (
        <div key={i} className="min-h-0 flex-1">
          <BlockView block={b} />
        </div>
      ))}
    </div>
  )
}
