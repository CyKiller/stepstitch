/**
 * Privacy-by-default redaction primitives.
 *
 * These are pure functions with no SDK state so the redaction-proof test suite can
 * assert them directly. Rule of thumb: anything readable is masked unless an element
 * is explicitly opted in. URLs are reduced to route templates. No input values, ever.
 */

import { MASKED } from "./types.js"

const DEFAULT_UNMASK_ATTR = "data-stepstitch-unmask"

/** Elements whose mere presence can leak NPI (rendered statements, IDs, photos). */
const BLOCKED_MEDIA_TAGS = new Set([
  "IMG",
  "SVG",
  "VIDEO",
  "CANVAS",
  "PICTURE",
  "AUDIO",
  "OBJECT",
  "EMBED",
  "MAP",
])

/** Inputs whose interaction must never be recorded at all. */
const SENSITIVE_INPUT_SELECTOR =
  'input[type="password"],input[autocomplete*="cc-"],[data-sensitive]'

/**
 * True when an element (or an ancestor) is explicitly opted in to unmasked capture.
 * Mirrors Sentry's `sentry-unmask` allowlist model.
 */
export function isUnmasked(
  el: Element | null,
  unmaskAttribute: string = DEFAULT_UNMASK_ATTR,
): boolean {
  let node: Element | null = el
  while (node) {
    if (node.hasAttribute(unmaskAttribute)) return true
    node = node.parentElement
  }
  return false
}

export function isSensitiveInput(el: Element | null): boolean {
  if (!el) return false
  return !!el.closest(SENSITIVE_INPUT_SELECTOR)
}

export function isBlockedMedia(el: Element | null): boolean {
  return !!el && BLOCKED_MEDIA_TAGS.has(el.tagName)
}

/**
 * Returns readable text ONLY when the element is unmasked; otherwise MASKED.
 * Caps length to avoid accidental large payloads even for allowed text.
 */
export function safeLabel(
  el: Element | null,
  unmaskAttribute: string = DEFAULT_UNMASK_ATTR,
): string {
  if (el && isUnmasked(el, unmaskAttribute)) {
    const text = (el.textContent ?? "").trim().replace(/\s+/g, " ")
    return text.slice(0, 40) || MASKED
  }
  return MASKED
}

/** CSS-escape an identifier so selectors are valid and injection-safe. */
function cssEscape(value: string): string {
  // Prefer the platform implementation when present (jsdom/browsers provide it).
  const g = globalThis as unknown as { CSS?: { escape?: (v: string) => string } }
  if (g.CSS && typeof g.CSS.escape === "function") return g.CSS.escape(value)
  return value.replace(/[^a-zA-Z0-9_-]/g, (c) => `\\${c}`)
}

/**
 * Build a stable, structural selector. Preference order:
 *   1. data-testid (test-stable, author-controlled, non-PII by convention)
 *   2. id
 *   3. tag + :nth-of-type path from the nearest id/testid ancestor or root
 * Never emits class names or attribute *values* that could carry PII.
 */
export function buildSelector(el: Element): string {
  const testId = el.getAttribute("data-testid")
  if (testId) return `[data-testid="${cssEscape(testId)}"]`
  if (el.id) return `#${cssEscape(el.id)}`

  const path: string[] = []
  let node: Element | null = el
  while (node && node.nodeType === 1 && path.length < 6) {
    const tag = node.tagName.toLowerCase()
    const anchorTestId = node.getAttribute("data-testid")
    if (anchorTestId) {
      path.unshift(`[data-testid="${cssEscape(anchorTestId)}"]`)
      break
    }
    if (node.id) {
      path.unshift(`#${cssEscape(node.id)}`)
      break
    }
    const parent: Element | null = node.parentElement
    if (parent) {
      const sameTag = Array.from(parent.children).filter(
        (c) => c.tagName === node!.tagName,
      )
      if (sameTag.length > 1) {
        const idx = sameTag.indexOf(node) + 1
        path.unshift(`${tag}:nth-of-type(${idx})`)
      } else {
        path.unshift(tag)
      }
    } else {
      path.unshift(tag)
    }
    node = parent
  }
  return path.join(" > ")
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const LONG_HEX_RE = /^[0-9a-f]{16,}$/i

/** A path segment is ID-like if it is numeric, a UUID, long hex, or contains digits. */
function isIdLikeSegment(seg: string): boolean {
  if (seg === "") return false
  if (/^\d+$/.test(seg)) return true
  if (UUID_RE.test(seg)) return true
  if (LONG_HEX_RE.test(seg)) return true
  if (/\d/.test(seg) && seg.length >= 6) return true
  return false
}

/**
 * Reduce a path to a route TEMPLATE. Strips query/hash entirely (query strings are a
 * common NPI carrier) and replaces ID-like segments with `:id`.
 *   `/accounts/8675309?ssn=1` -> `/accounts/:id`
 */
export function routeTemplate(pathname: string): string {
  const path = pathname.split("?")[0]!.split("#")[0]!
  const segments = path.split("/").map((seg) => {
    const decoded = safeDecode(seg)
    return isIdLikeSegment(decoded) ? ":id" : decoded
  })
  const joined = segments.join("/")
  return joined === "" ? "/" : joined
}

function safeDecode(seg: string): string {
  try {
    return decodeURIComponent(seg)
  } catch {
    return seg
  }
}
