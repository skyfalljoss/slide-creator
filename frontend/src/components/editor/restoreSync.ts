import type { DeckStatus, OnlyOfficeEditorConfig } from '@/types'

export function restoredSnapshotError(
  deckId: string,
  expected: DeckStatus,
  status: DeckStatus | undefined,
  editorConfig: OnlyOfficeEditorConfig | undefined,
): string | null {
  if (status?.current_version_id !== expected.current_version_id) {
    return 'The restored status is not current yet.'
  }
  const document = editorConfig?.config.document
  const key = document && typeof document === 'object'
    ? (document as { key?: unknown }).key
    : undefined
  if (key !== `${deckId}-${expected.current_version_id}`) {
    return 'The restored editor config is not current yet.'
  }
  return null
}
