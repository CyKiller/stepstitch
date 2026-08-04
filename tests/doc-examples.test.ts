/**
 * Every published code example compiles.
 *
 * The README and getting-started snippets are what a prospect pastes first; a
 * snippet that no longer type-checks against the real SDK is a broken promise
 * discovered by the least-forgiving audience. This suite extracts the marked
 * fences and compiles them against the ACTUAL package source (src/index.ts) —
 * not a copy — so an SDK API change that breaks a doc fails CI in this repo,
 * not in a customer's editor.
 *
 * TS snippets are type-checked with the TypeScript compiler API under strict
 * mode; JS snippets are syntax-checked by Node itself (`node --check`, as an
 * ES module, matching how the docs present them).
 */
import { execFileSync } from "node:child_process"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import ts from "typescript"
import { describe, expect, it } from "vitest"

import { extractDocExamples, type DocExample } from "./doc-examples/extract.js"

const ROOT = path.resolve(__dirname, "..")

function examplesFrom(relPath: string): Map<string, DocExample> {
  const markdown = fs.readFileSync(path.join(ROOT, relPath), "utf8")
  return new Map(extractDocExamples(markdown).map((e) => [e.id, e]))
}

const README = examplesFrom("README.md")
const GETTING_STARTED = examplesFrom("docs/getting-started.md")

/**
 * Snippets are fragments of a host app, so identifiers the surrounding app
 * would provide (an HTTP response, the current project id) are declared here
 * rather than cluttering the docs. Everything else must type-check for real.
 */
const SNIPPET_PREAMBLE = [
  "declare const res: Response",
  "declare const projectId: string",
  "",
].join("\n")

function typeCheck(code: string): string[] {
  const fileName = path.join(ROOT, "__doc_snippet__.ts")
  const full = SNIPPET_PREAMBLE + code
  const options: ts.CompilerOptions = {
    strict: true,
    noEmit: true,
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    lib: ["lib.es2022.d.ts", "lib.dom.d.ts"],
    baseUrl: ROOT,
    // The docs import the published name; resolve it to the real source so the
    // check follows the SDK, not a stale build.
    paths: { "@stepstitch/tracker": ["src/index.ts"] },
  }
  const host = ts.createCompilerHost(options)
  const readFile = host.readFile.bind(host)
  const fileExists = host.fileExists.bind(host)
  const getSourceFile = host.getSourceFile.bind(host)
  host.readFile = (fn) => (fn === fileName ? full : readFile(fn))
  host.fileExists = (fn) => fn === fileName || fileExists(fn)
  host.getSourceFile = (fn, langVersion, ...rest) =>
    fn === fileName
      ? ts.createSourceFile(fn, full, langVersion, true)
      : getSourceFile(fn, langVersion, ...rest)
  const program = ts.createProgram([fileName], options, host)
  return ts.getPreEmitDiagnostics(program).map((d) => {
    const where =
      d.file && d.start !== undefined
        ? `:${d.file.getLineAndCharacterOfPosition(d.start).line + 1}`
        : ""
    return `${where} ${ts.flattenDiagnosticMessageText(d.messageText, "\n")}`
  })
}

function syntaxCheckAsModule(code: string): void {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "stepstitch-doc-"))
  const file = path.join(dir, "snippet.mjs")
  try {
    fs.writeFileSync(file, code)
    execFileSync(process.execPath, ["--check", file], { stdio: "pipe" })
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
}

describe("doc-example inventory", () => {
  it("README marks exactly the expected snippets", () => {
    expect([...README.keys()].sort()).toEqual(["ingest-proxy-js", "usage-ts"])
  })

  it("getting-started marks exactly the expected snippets", () => {
    expect([...GETTING_STARTED.keys()].sort()).toEqual(["wire-up-ts"])
  })
})

describe("published TypeScript examples type-check against the real SDK", () => {
  const cases: Array<[string, DocExample]> = [
    ["README usage-ts", README.get("usage-ts")!],
    ["getting-started wire-up-ts", GETTING_STARTED.get("wire-up-ts")!],
  ]

  it.each(cases)("%s", (_name, example) => {
    expect(example).toBeDefined()
    expect(example.lang).toBe("ts")
    const diagnostics = typeCheck(example.code)
    expect(diagnostics, diagnostics.join("\n")).toEqual([])
  })

  it("the checker itself catches a broken snippet (self-test)", () => {
    const diagnostics = typeCheck(
      'import { StepStitchTracker } from "@stepstitch/tracker"\n' +
        'new StepStitchTracker({ appId: 42 })\n',
    )
    expect(diagnostics.length).toBeGreaterThan(0)
  })
})

describe("published JavaScript examples parse as the modules they claim to be", () => {
  it("README ingest-proxy-js", () => {
    const example = README.get("ingest-proxy-js")!
    expect(example.lang).toBe("js")
    syntaxCheckAsModule(example.code)
  })

  it("the checker itself catches a syntax error (self-test)", () => {
    expect(() => syntaxCheckAsModule("export async function POST( {")).toThrow()
  })
})
