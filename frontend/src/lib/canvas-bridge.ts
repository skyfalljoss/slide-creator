import type { SlideData } from '@/types'

export interface CanvasObject {
  type: string
  role?: string
  text?: string
  left?: number
  top?: number
  width?: number
  height?: number
  fontSize?: number
  fontFamily?: string
  fontWeight?: string | number
  fill?: string
  stroke?: string
  strokeWidth?: number
  fontStyle?: string
  textAlign?: string
  selectable?: boolean
  evented?: boolean
  rx?: number
  ry?: number
  [key: string]: unknown
}

const CANVAS_W = 960
const CANVAS_H = 540
const PPTX_W = 17.7778
const PPTX_H = 10
const LEFT_MARGIN = 0.83
const CONTENT_WIDTH = PPTX_W - LEFT_MARGIN * 2
const CONTENT_BOTTOM = 8.9
const ACCENT_RULE_WIDTH = 1.4
const ACCENT_RULE_HEIGHT = 0.05

const COLORS = {
  darkBg: '#0F1B2D',
  darkPanel: '#162438',
  darkPanelBorder: '#334155',
  darkText: '#F1F5F9',
  darkMuted: '#9FADBD',
  darkAccent: '#F26A5F',
  darkAccentSoft: '#3A2022',
  lightBg: '#F8FAFC',
  lightTopPanel: '#F0F3F7',
  lightBottomPanel: '#F1F5F9',
  lightText: '#003B70',
  lightMuted: '#5B6770',
  lightAccent: '#EE2A24',
  lightAccentSoft: '#FBE2E1',
  lightSurface: '#FBFCFE',
  lightBorder: '#DCE0E5',
}

const DARK_VARIANTS = new Set(['big_statement', 'big_stat', 'quote', 'closing'])

function x(inches: number, width = CANVAS_W): number {
  return Math.round((inches / PPTX_W) * width)
}

function y(inches: number, height = CANVAS_H): number {
  return Math.round((inches / PPTX_H) * height)
}

function w(inches: number, width = CANVAS_W): number {
  return x(inches, width)
}

function h(inches: number, height = CANVAS_H): number {
  return y(inches, height)
}

function pt(size: number, height = CANVAS_H): number {
  return Math.round(size * (height / (PPTX_H * 72)))
}

function rect(
  role: string,
  left: number,
  top: number,
  width: number,
  height: number,
  fill: string,
  options: Partial<CanvasObject> = {},
): CanvasObject {
  return {
    type: 'rect',
    role,
    left,
    top,
    width,
    height,
    fill,
    selectable: false,
    evented: false,
    ...options,
  }
}

function text(
  role: string,
  value: string,
  left: number,
  top: number,
  width: number,
  fontSize: number,
  fill: string,
  options: Partial<CanvasObject> = {},
): CanvasObject {
  return {
    type: 'text',
    role,
    text: value,
    left,
    top,
    width,
    fontSize,
    fontFamily: options.fontWeight === 'bold' || fontSize >= 21 ? 'Aptos Display' : 'Aptos',
    fill,
    ...options,
  }
}

function titleHeight(title: string, logicalWidth: number): number {
  const charsPerLine = Math.max(18, Math.floor(logicalWidth / 0.44))
  const lines = Math.max(1, Math.ceil((title || '').length / charsPerLine))
  return Math.min(Math.max(1.25, lines * 0.72), 3.25)
}

function isDarkSlide(slide: SlideData): boolean {
  if (slide.index === 1 || slide.layout === 'title') return true
  return DARK_VARIANTS.has(slide.variant || '')
}

function addBackground(objects: CanvasObject[], dark: boolean, width: number, height: number) {
  if (dark) {
    objects.push(rect('background', 0, 0, width, height, COLORS.darkBg))
    objects.push(rect('depth-panel-right', x(13.25, width), 0, w(4.53, width), height, COLORS.darkPanel))
    objects.push(rect('depth-panel-bottom', 0, y(8.95, height), width, h(1.05, height), '#0B1626'))
    return
  }

  objects.push(rect('background', 0, 0, width, height, COLORS.lightBg))
  objects.push(rect('depth-panel-top', 0, 0, width, h(1.1, height), COLORS.lightTopPanel))
  objects.push(rect('depth-panel-bottom', 0, y(8.85, height), width, h(1.15, height), COLORS.lightBottomPanel))
}

function addEyebrow(objects: CanvasObject[], label: string, left: number, top: number, maxWidth = 12, dark = false) {
  const upper = label.toUpperCase()
  const pillW = Math.min(Math.max(1.45, upper.length * 0.105 + 0.55), maxWidth)
  objects.push(rect('eyebrow-pill', x(left), y(top - 0.05), w(pillW), h(0.42), dark ? COLORS.darkAccentSoft : COLORS.lightAccentSoft, {
    stroke: dark ? COLORS.darkAccent : COLORS.lightAccent,
    strokeWidth: 1,
    rx: 12,
    ry: 12,
  }))
  objects.push(text('kicker', upper, x(left + 0.18), y(top + 0.03), w(Math.max(pillW - 0.36, 0.5)), pt(12), dark ? COLORS.darkAccent : COLORS.lightAccent, {
    fontWeight: 'bold',
  }))
}

function addAccentBar(objects: CanvasObject[], left: number, top: number, width = ACCENT_RULE_WIDTH, height = ACCENT_RULE_HEIGHT, dark = false) {
  objects.push(rect('accent-bar', x(left), y(top), w(width), Math.max(3, h(height)), dark ? COLORS.darkAccent : COLORS.lightAccent))
}

function addBrand(objects: CanvasObject[], dark: boolean) {
  objects.push(text('brand', 'citi', x(16.25), y(0.2), w(1.0), pt(16), dark ? COLORS.darkAccent : COLORS.lightAccent, {
    fontWeight: 'bold',
    selectable: false,
    evented: false,
    textAlign: 'right',
  }))
}

function addCoverVisualPanel(objects: CanvasObject[], width: number, height: number) {
  const left = 10.15
  const top = 0.92
  const panelW = 6.8
  const panelH = 8.14
  objects.push(rect('cover-panel', x(left, width), y(top, height), w(panelW, width), h(panelH, height), COLORS.darkPanel, {
    stroke: COLORS.darkPanelBorder,
    strokeWidth: 1,
  }))
  for (const [offset, stripeW] of [[0.55, 0.08], [1.05, 0.04], [1.55, 0.04]] as const) {
    objects.push(rect('cover-stripe', x(left + offset, width), y(top + 0.65, height), w(stripeW, width), h(panelH - 1.3, height), COLORS.darkAccent))
  }
}

function renderTitleSlide(slide: SlideData, width: number, height: number): CanvasObject[] {
  const objects: CanvasObject[] = []
  addBackground(objects, true, width, height)
  addCoverVisualPanel(objects, width, height)

  if (slide.kicker) {
    addEyebrow(objects, slide.kicker, LEFT_MARGIN, 3.05, 12, true)
  }

  const titleTop = 3.45
  const titleW = 8.9
  const titleH = titleHeight(slide.title, titleW)
  objects.push(text('title', slide.title, x(LEFT_MARGIN, width), y(titleTop, height), w(titleW, width), pt(48, height), COLORS.darkText, {
    fontWeight: 'bold',
    height: h(titleH, height),
  }))

  const accentTop = titleTop + titleH + 0.22
  addAccentBar(objects, LEFT_MARGIN, accentTop, ACCENT_RULE_WIDTH, 0.06, true)

  const subtitle = slide.subtitle || (slide.bullets[0] || '')
  const secondary = slide.subtitle ? slide.bullets : slide.bullets.slice(1)
  const subtitleTop = accentTop + 0.25
  if (subtitle) {
    objects.push(text('subtitle', subtitle, x(LEFT_MARGIN, width), y(subtitleTop, height), w(9.0, width), pt(22, height), COLORS.darkMuted))
  }
  secondary.forEach((bullet, i) => {
    objects.push(text('bullet', `• ${bullet}`, x(LEFT_MARGIN, width), y(subtitleTop + 0.92 + i * 0.42, height), w(9.2, width), pt(18, height), COLORS.darkText))
  })
  addBrand(objects, true)
  return objects
}

function addContentHeader(objects: CanvasObject[], slide: SlideData, dark: boolean): number {
  const titleColor = dark ? COLORS.darkText : COLORS.lightText
  const mutedColor = dark ? COLORS.darkMuted : COLORS.lightMuted
  const kicker = slide.kicker || ''
  if (kicker) {
    addEyebrow(objects, kicker, LEFT_MARGIN, 0.62, 12, dark)
    objects.push(text('title', slide.title, x(LEFT_MARGIN), y(1.02), w(16.11), pt(30), titleColor, {
      fontWeight: 'bold',
      height: h(0.9),
    }))
  } else {
    objects.push(text('title', slide.title, x(LEFT_MARGIN), y(0.66), w(16.11), pt(30), titleColor, {
      fontWeight: 'bold',
      height: h(0.9),
    }))
  }

  const ruleTop = kicker ? 1.78 : 1.6
  addAccentBar(objects, LEFT_MARGIN, ruleTop, ACCENT_RULE_WIDTH, ACCENT_RULE_HEIGHT, dark)
  let top = ruleTop + 0.45
  if (slide.subtitle) {
    objects.push(text('subtitle', slide.subtitle, x(LEFT_MARGIN), y(top), w(16.11), pt(18), mutedColor, { height: h(0.5) }))
    top += 0.65
  }
  return top
}

function renderContentSlide(slide: SlideData, width: number, height: number): CanvasObject[] {
  const dark = isDarkSlide(slide)
  const objects: CanvasObject[] = []
  addBackground(objects, dark, width, height)

  const textColor = dark ? COLORS.darkText : COLORS.lightText
  const mutedColor = dark ? COLORS.darkMuted : COLORS.lightMuted
  const surface = dark ? COLORS.darkPanel : COLORS.lightSurface
  const border = dark ? COLORS.darkPanelBorder : COLORS.lightBorder
  let top = addContentHeader(objects, slide, dark)

  if (slide.callout) {
    objects.push(rect('callout-box', x(LEFT_MARGIN, width), y(top, height), w(CONTENT_WIDTH, width), h(0.6, height), dark ? COLORS.darkAccentSoft : COLORS.lightAccentSoft, {
      stroke: dark ? COLORS.darkAccent : COLORS.lightAccent,
      strokeWidth: 1,
      rx: 8,
      ry: 8,
    }))
    objects.push(text('callout', slide.callout, x(LEFT_MARGIN + 0.25, width), y(top + 0.12, height), w(CONTENT_WIDTH - 0.5, width), pt(14, height), textColor, {
      fontStyle: 'italic',
    }))
    top += 0.85
  }

  if (slide.chart_data) {
    objects.push(rect('bullet-panel', x(LEFT_MARGIN, width), y(top, height), w(6.0, width), h(8.6 - top, height), surface, {
      stroke: border,
      strokeWidth: 1,
      rx: 10,
      ry: 10,
    }))
    slide.bullets.forEach((bullet, i) => {
      objects.push(text('bullet', `• ${bullet}`, x(LEFT_MARGIN + 0.35, width), y(top + 0.45 + i * 0.48, height), w(5.3, width), pt(18, height), textColor))
    })
    objects.push(rect('divider', x(7.1, width), y(top, height), Math.max(1, w(0.01, width)), h(8.4 - top, height), border))
    objects.push(rect('chart-panel', x(7.5, width), y(top, height), w(9.44, width), h(8.0 - top, height), surface, {
      stroke: border,
      strokeWidth: 1,
      rx: 10,
      ry: 10,
    }))
    objects.push(text('chart-title', slide.chart_data.title || 'Chart', x(7.9, width), y(top + 0.35, height), w(8.5, width), pt(18, height), textColor, { fontWeight: 'bold' }))
    addBrand(objects, dark)
    return objects
  }

  if (slide.bullets.length > 0) {
    const panelH = Math.min(CONTENT_BOTTOM - top, 5.9)
    objects.push(rect('bullet-panel', x(LEFT_MARGIN, width), y(top, height), w(10.8, width), h(panelH, height), surface, {
      stroke: border,
      strokeWidth: 1,
      rx: 10,
      ry: 10,
    }))
    addAccentBar(objects, LEFT_MARGIN + 0.48, top + 0.52, 1.0, 0.05, dark)
    slide.bullets.forEach((bullet, i) => {
      objects.push(text('bullet', `• ${bullet}`, x(LEFT_MARGIN + 0.55, width), y(top + 0.95 + i * 0.5, height), w(9.4, width), pt(18, height), textColor))
    })
  } else {
    objects.push(rect('visual-panel', x(LEFT_MARGIN, width), y(top, height), w(CONTENT_WIDTH, width), h(CONTENT_BOTTOM - top, height), dark ? COLORS.darkPanel : COLORS.lightTopPanel, {
      stroke: dark ? COLORS.darkPanel : COLORS.lightTopPanel,
    }))
    objects.push(rect('visual-panel-stripe', x(LEFT_MARGIN, width), y(top, height), w(0.08, width), h(CONTENT_BOTTOM - top, height), dark ? COLORS.darkAccent : COLORS.lightAccent))
    objects.push(text('visual-panel-title', 'Visual Direction & Context', x(LEFT_MARGIN + 0.35, width), y(top + 0.35, height), w(CONTENT_WIDTH - 0.7, width), pt(16, height), dark ? COLORS.darkAccent : COLORS.lightAccent, { fontWeight: 'bold' }))
    objects.push(text('visual-panel-body', slide.visual_direction || "Use a clean Citi-style callout visual for the slide's core message.", x(LEFT_MARGIN + 0.35, width), y(top + 0.9, height), w(CONTENT_WIDTH - 0.7, width), pt(16, height), mutedColor))
  }

  addBrand(objects, dark)
  return objects
}

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
  bgColor?: string,
): CanvasObject[] {
  const objects = slide.index === 1 || slide.layout === 'title'
    ? renderTitleSlide(slide, width, height)
    : renderContentSlide(slide, width, height)
  const background = objects.find((object) => object.role === 'background')
  if (background && bgColor) background.fill = bgColor
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

  const title = texts.find((t) => t.role === 'title')
  if (title?.text) result.title = title.text

  const kicker = texts.find((t) => t.role === 'kicker') ?? texts.find((t) => (t.top ?? 0) <= 50)
  if (kicker) result.kicker = kicker.text ?? null

  const subtitle = texts.find((t) => t.role === 'subtitle')
  if (subtitle) result.subtitle = subtitle.text ?? null

  const bullets = texts
    .filter((t) => t.role === 'bullet' || t.text?.startsWith('• '))
    .map((t) => (t.text || '').replace(/^• /, ''))
    .filter(Boolean)
  result.bullets = bullets

  if (!title) {
    const fallbackTitle = texts.find((t) => (t.top ?? 0) > y(0.45) && (t.top ?? 0) <= y(2.1))
    if (fallbackTitle?.text) result.title = fallbackTitle.text
  }

  return result
}
