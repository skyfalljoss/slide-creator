import type { SlideData } from '@/types'

interface CanvasObject {
  type: string
  text?: string
  left?: number
  top?: number
  width?: number
  height?: number
  fontSize?: number
  fontFamily?: string
  fontWeight?: string | number
  fill?: string
  fontStyle?: string
  selectable?: boolean
  evented?: boolean
  rx?: number
  ry?: number
  [key: string]: unknown
}

const CANVAS_W = 960
const CANVAS_H = 540

const TITLE_TOP = 80
const KICKER_TOP = 40
const BULLETS_START_TOP = 220
const BULLET_LINE_HEIGHT = 40

export function createEmptySlide(index: number): SlideData {
  return {
    index,
    title: 'New Slide',
    bullets: [],
    notes: '',
    layout: 'content',
    variant: null,
    chart_data: null,
  }
}

export function slideToCanvasObjects(
  slide: SlideData,
  width: number = CANVAS_W,
  height: number = CANVAS_H,
  bgColor: string = '#1E293B',
): CanvasObject[] {
  const objects: CanvasObject[] = []

  objects.push({
    type: 'rect',
    left: 0,
    top: 0,
    width,
    height,
    fill: bgColor,
    selectable: false,
    evented: false,
  })

  if (slide.kicker) {
    objects.push({
      type: 'text',
      text: slide.kicker,
      left: 60,
      top: KICKER_TOP,
      fontSize: 14,
      fontFamily: 'Inter',
      fontWeight: '700',
      fill: '#E31837',
    })
  }

  objects.push({
    type: 'text',
    text: slide.title,
    left: 60,
    top: slide.kicker ? TITLE_TOP + 30 : KICKER_TOP + 20,
    fontSize: 32,
    fontFamily: 'Inter',
    fontWeight: 'bold',
    fill: '#FFFFFF',
  })

  if (slide.subtitle) {
    const titleObj = objects[objects.length - 1]
    const titleBottom = (titleObj.top as number) + 48
    objects.push({
      type: 'text',
      text: slide.subtitle,
      left: 60,
      top: titleBottom + 10,
      fontSize: 16,
      fontFamily: 'Inter',
      fill: '#94A3B8',
    })
  }

  const subtitleBottom = slide.subtitle ? ((objects[objects.length - 1].top as number) + 28) : 0
  let contentTop = Math.max(BULLETS_START_TOP, subtitleBottom + 20)

  if (slide.callout) {
    objects.push({
      type: 'rect',
      left: 60,
      top: contentTop,
      width: width - 120,
      height: 36,
      fill: 'rgba(5,109,174,0.15)',
      rx: 4,
      ry: 4,
      selectable: false,
    })
    objects.push({
      type: 'text',
      text: slide.callout,
      left: 72,
      top: contentTop + 8,
      fontSize: 14,
      fontFamily: 'Inter',
      fontStyle: 'italic',
      fill: '#056DAE',
    })
    contentTop += 50
  }

  slide.bullets.forEach((bullet, i) => {
    objects.push({
      type: 'text',
      text: `• ${bullet}`,
      left: 60,
      top: contentTop + i * BULLET_LINE_HEIGHT,
      fontSize: 14,
      fontFamily: 'Inter',
      fill: '#CBD5E1',
      width: width - 120,
    })
  })

  return objects
}

export function canvasObjectsToSlide(
  objects: CanvasObject[],
  originalSlide: SlideData,
): SlideData {
  const texts = objects
    .filter((o) => o.type === 'text' && o.text !== undefined)
    .sort((a, b) => (a.top ?? 0) - (b.top ?? 0))

  const result: SlideData = { ...originalSlide }

  const filtered = texts.filter((t) => t.text !== undefined)

  const kicker = filtered.find((t) => (t.top ?? 0) <= KICKER_TOP + 10)
  if (kicker) {
    result.kicker = kicker.text ?? null
  }

  const titleCandidates = filtered.filter((t) => (t.top ?? 0) > KICKER_TOP + 10 && (t.top ?? 0) <= TITLE_TOP + 60)
  if (titleCandidates.length > 0) {
    result.title = titleCandidates[0].text!
  }

  const potentiallySubtitle = filtered.filter((t) => (t.top ?? 0) > TITLE_TOP + 30 && (t.top ?? 0) < BULLETS_START_TOP)
  if (potentiallySubtitle.length > 0) {
    result.subtitle = potentiallySubtitle[0].text ?? null
  }

  const bullets = filtered
    .filter((t) => (t.top ?? 0) >= BULLETS_START_TOP - 10)
    .filter((t) => t.text!.startsWith('• '))
    .map((t) => t.text!.replace(/^• /, ''))

  result.bullets = bullets
  return result
}
