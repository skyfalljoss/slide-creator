export interface ChartSeries {
  name: string
  values: number[]
}

export interface ChartData {
  type: 'bar' | 'line' | 'waterfall'
  title: string
  categories: string[]
  series: ChartSeries[]
}

export interface ChartRecommendation {
  chart_type: 'bar' | 'line' | 'waterfall'
  category_column: string
  value_columns: string[]
  rationale: string
}

export interface ChartAudit {
  source_filename: string
  category_column: string
  value_columns: string[]
  row_count: number
  chart_type: 'bar' | 'line' | 'waterfall'
  recommendation_status: 'accepted' | 'rejected' | 'not_requested'
  rejection_reason: string | null
}

export interface SlideData {
  index: number
  title: string
  kicker?: string | null
  subtitle?: string | null
  chapter_number?: 1 | 2 | 3 | 4 | null
  chapter_title?: string | null
  bullets: string[]
  notes: string
  layout: string
  variant?: 'cover' | 'big_statement' | 'three_points' | 'split_image' | 'big_stat' | 'before_after' | 'comparison_table' | 'process' | 'quote' | 'closing' | null
  blocks?: SlideBlock[] | null
  chart_data: ChartData | null
  visual_direction?: string | null
  callout?: string | null
  narrative_context?: string | null
  chart_recommendation?: ChartRecommendation | null
  chart_audit?: ChartAudit | null
  image_query?: string | null
}

export interface SlideBlockItem {
  title?: string
  body?: string
  text?: string
  icon?: string
}

export interface SlideBlock {
  type: string
  value?: string
  number?: string
  label?: string
  caption?: string
  text?: string
  quote?: string
  author?: string
  columns?: number
  items?: Array<string | SlideBlockItem>
  cards?: Array<string | SlideBlockItem>
  headers?: string[]
  rows?: string[][]
  steps?: Array<string | SlideBlockItem>
}

export type DeckType = 'sales_9' | 'internal_6'

export interface GenerateRequest {
  prompt: string
  deck_type: DeckType
  source_type?: 'brief' | 'script'
  target_audience?: 'corporate' | 'casual' | 'academic'
  theme?: 'minimalist' | 'bold' | 'dark'
  aspect_ratio?: '16:9' | '4:3'
  file_id?: string | null
}

export interface GenerateResponse {
  session_id: string
  slides: SlideData[]
}

export interface UploadResponse {
  file_id: string
  filename: string
  row_count: number
  columns: string[]
  preview: string
}

export interface RefineRequest {
  session_id: string
  slide_index: number
  instruction: string
}

export interface RefineResponse {
  slide: SlideData
}

export interface ExportRequest {
  session_id?: string | null
  deck_id?: string | null
}

export interface ExportResponse {
  download_url: string
  expires_at: string
}

export interface SlidePreviewResponse {
  deck_id: string
  slide_index: number
  image_b64: string
  width: number
  height: number
  updated_at: string | null
}

export interface DeckState {
  sessionId: string | null
  savedDeckId: string | null
  deckType: DeckType | null
  slides: SlideData[]
  uploadedFile: UploadResponse | null
  lastExport: ExportResponse | null
}

export interface DeckSummary {
  id: string
  name: string
  deck_type: DeckType
  slide_count: number
  thumbnail_b64: string | null
  created_at: string
  updated_at: string
}

export interface DeckDetail {
  id: string
  name: string
  deck_type: DeckType
  theme: string
  aspect_ratio: string
  slides: SlideData[]
  thumbnail_b64: string | null
  created_at: string
  updated_at: string
}

export interface SaveDeckRequest {
  name: string
  deck_type: DeckType
  theme: string
  aspect_ratio: string
  slides: SlideData[]
  thumbnail_b64?: string | null
}

export interface SaveDeckResponse {
  id: string
  name: string
  created_at: string
}

export interface UpdateDeckRequest {
  name?: string
  slides?: SlideData[]
}

export interface UpdateDeckResponse {
  updated_at: string
}

export interface ListDecksResponse {
  decks: DeckSummary[]
}
