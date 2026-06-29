import { useEffect, useRef, type ReactNode, type RefObject } from 'react'
import { cn } from '@/lib/utils'

interface AccessibleModalProps {
  open: boolean
  labelledBy: string
  initialFocusRef: RefObject<HTMLElement | null>
  onRequestClose: () => void
  canClose?: boolean
  overlayClassName?: string
  children: ReactNode
}

const FOCUSABLE_SELECTOR = [
  'button:not(:disabled)',
  'a[href]',
  'input:not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

export function AccessibleModal({
  open,
  labelledBy,
  initialFocusRef,
  onRequestClose,
  canClose = true,
  overlayClassName,
  children,
}: AccessibleModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const overlay = overlayRef.current
    const parent = overlay?.parentElement
    const backgroundElements = parent
      ? Array.from(parent.children).filter((element): element is HTMLElement => (
          element instanceof HTMLElement && element !== overlay
        ))
      : []
    const originalState = backgroundElements.map((element) => ({
      element,
      ariaHidden: element.getAttribute('aria-hidden'),
      inert: element.hasAttribute('inert'),
    }))
    for (const element of backgroundElements) {
      element.setAttribute('aria-hidden', 'true')
      element.setAttribute('inert', '')
    }
    initialFocusRef.current?.focus()

    return () => {
      for (const { element, ariaHidden, inert } of originalState) {
        if (ariaHidden === null) element.removeAttribute('aria-hidden')
        else element.setAttribute('aria-hidden', ariaHidden)
        if (!inert) element.removeAttribute('inert')
      }
      opener?.focus()
    }
  }, [initialFocusRef, open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && canClose) {
        event.preventDefault()
        onRequestClose()
        return
      }
      if (event.key !== 'Tab') return
      const elements = overlayRef.current
        ? Array.from(overlayRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
        : []
      if (elements.length === 0) {
        event.preventDefault()
        return
      }
      const first = elements[0]
      const last = elements[elements.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [canClose, onRequestClose, open])

  if (!open) return null
  return (
    <div
      ref={overlayRef}
      data-modal-overlay={labelledBy}
      className={cn('fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4', overlayClassName)}
      onMouseDown={(event) => {
        if (canClose && event.target === event.currentTarget) onRequestClose()
      }}
    >
      <section role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
        {children}
      </section>
    </div>
  )
}
