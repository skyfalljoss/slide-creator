import { describe, it, expect } from 'vitest'
import { createEmptySlide, slideToCanvasObjects, canvasObjectsToSlide } from './canvas-bridge'
import type { SlideData } from '@/types'

describe('createEmptySlide', () => {
  it('returns a minimal blank slide', () => {
    const slide = createEmptySlide(5)
    expect(slide.index).toBe(5)
    expect(slide.title).toBe('New Slide')
    expect(slide.bullets).toEqual([])
    expect(slide.layout).toBe('content')
    expect(slide.variant).toBeNull()
    expect(slide.notes).toBe('')
  })
})

describe('slideToCanvasObjects', () => {
  it('creates background rect', () => {
    const slide: SlideData = { index: 1, title: 'Test', bullets: [], notes: '', layout: 'content', chart_data: null }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    expect(objects.length).toBeGreaterThanOrEqual(1)
    expect(objects[0].type).toBe('rect')
    expect(objects[0].width).toBe(960)
    expect(objects[0].height).toBe(540)
    expect(objects[0].fill).toBe('#056DAE')
  })

  it('creates title textbox', () => {
    const slide: SlideData = { index: 1, title: 'Hello', bullets: [], notes: '', layout: 'content', chart_data: null }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    const title = objects.find((o: any) => o.type === 'text' && o.text === 'Hello')
    expect(title).toBeDefined()
  })

  it('creates bullet textboxes with prefix', () => {
    const slide: SlideData = { index: 1, title: 'X', bullets: ['Point A', 'Point B'], notes: '', layout: 'content', chart_data: null }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    const bullets = objects.filter((o: any) => o.type === 'text' && o.text && o.text.startsWith('• '))
    expect(bullets).toHaveLength(2)
    expect(bullets[0].text).toBe('• Point A')
    expect(bullets[1].text).toBe('• Point B')
  })

  it('creates kicker textbox when present', () => {
    const slide: SlideData = { index: 1, title: 'X', kicker: 'SECTION A', bullets: [], notes: '', layout: 'content', chart_data: null }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    const kicker = objects.find((o: any) => o.type === 'text' && o.text === 'SECTION A')
    expect(kicker).toBeDefined()
  })
})

describe('canvasObjectsToSlide', () => {
  it('extracts title from canvas objects', () => {
    const objects = [
      { type: 'rect', left: 0, top: 0 },
      { type: 'text', text: 'My Title', left: 60, top: 80, fontSize: 32, fontFamily: 'Inter', fontWeight: 'bold' },
    ]
    const result = canvasObjectsToSlide(objects, { index: 1, title: '', bullets: [], notes: '', layout: 'content', chart_data: null })
    expect(result.title).toBe('My Title')
  })

  it('extracts bullets from content area', () => {
    const objects = [
      { type: 'rect', left: 0, top: 0 },
      { type: 'text', text: 'Title', left: 60, top: 80 },
      { type: 'text', text: '• Bullet 1', left: 60, top: 220 },
      { type: 'text', text: '• Bullet 2', left: 60, top: 260 },
    ]
    const result = canvasObjectsToSlide(objects, { index: 1, title: '', bullets: [], notes: '', layout: 'content', chart_data: null })
    expect(result.bullets).toEqual(['Bullet 1', 'Bullet 2'])
  })

  it('extracts kicker from top area', () => {
    const objects = [
      { type: 'rect', left: 0, top: 0 },
      { type: 'text', text: 'KICKER', left: 60, top: 40, fontSize: 12 },
      { type: 'text', text: 'Title', left: 60, top: 80 },
    ]
    const result = canvasObjectsToSlide(objects, { index: 1, title: '', bullets: [], notes: '', layout: 'content', chart_data: null })
    expect(result.kicker).toBe('KICKER')
  })
})
