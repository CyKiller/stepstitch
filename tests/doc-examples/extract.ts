/**
 * Pull marked code snippets out of the published markdown so a test can compile
 * them. A snippet is opted in with an HTML comment on the line before its fence:
 *
 *     <!-- doc-example:usage-ts -->
 *     ```ts
 *     ...
 *     ```
 *
 * The id is the test's handle; the inventory assertion in doc-examples.test.ts
 * pins the full id list per file, so a new snippet must either be marked (and
 * added to the inventory) or consciously left out — it cannot silently escape
 * coverage.
 */

export type DocExample = {
  id: string
  lang: string
  code: string
}

const MARKED_FENCE =
  /<!--\s*doc-example:([a-z0-9-]+)\s*-->\s*\r?\n```(\w+)\r?\n([\s\S]*?)```/g

export function extractDocExamples(markdown: string): DocExample[] {
  const out: DocExample[] = []
  for (const match of markdown.matchAll(MARKED_FENCE)) {
    out.push({ id: match[1]!, lang: match[2]!, code: match[3]! })
  }
  return out
}
