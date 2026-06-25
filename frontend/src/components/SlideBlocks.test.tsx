import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SlideBlocks } from './SlideBlocks'
import type { SlideBlock } from '@/types'

describe('SlideBlocks', () => {
  it('renders a stat block', () => {
    const blocks: SlideBlock[] = [{ type: 'stat', value: '48%', label: 'Cost reduction' }]
    render(<SlideBlocks blocks={blocks} />)
    expect(screen.getByText('48%')).toBeInTheDocument()
    expect(screen.getByText('Cost reduction')).toBeInTheDocument()
  })

  it('renders a quote block with author', () => {
    const blocks: SlideBlock[] = [{ type: 'quote', text: 'Build the future', author: 'Jane Doe' }]
    render(<SlideBlocks blocks={blocks} />)
    expect(screen.getByText(/Build the future/)).toBeInTheDocument()
    expect(screen.getByText('Jane Doe')).toBeInTheDocument()
  })

  it('renders a table block', () => {
    const blocks: SlideBlock[] = [{ type: 'table', headers: ['Feature', 'New'], rows: [['Compliance', 'Native']] }]
    render(<SlideBlocks blocks={blocks} />)
    expect(screen.getByText('Feature')).toBeInTheDocument()
    expect(screen.getByText('Native')).toBeInTheDocument()
  })

  it('renders cards with titles', () => {
    const blocks: SlideBlock[] = [{ type: 'cards', items: [{ title: 'Velocity', body: 'Fast' }, { title: 'Security', body: 'Safe' }] }]
    render(<SlideBlocks blocks={blocks} />)
    expect(screen.getByText('Velocity')).toBeInTheDocument()
    expect(screen.getByText('Security')).toBeInTheDocument()
  })

  it('renders numbered process steps', () => {
    const blocks: SlideBlock[] = [{ type: 'process', steps: [{ title: 'Audit' }, { title: 'Migrate' }] }]
    render(<SlideBlocks blocks={blocks} />)
    expect(screen.getByText('Audit')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })
})
