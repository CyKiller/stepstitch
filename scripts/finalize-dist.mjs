// Dual-package finalizer: the repo is ESM ("type": "module"), so files under dist/ are
// treated as ESM. The CJS build lands in dist/cjs/ — mark that subtree as CommonJS with a
// nested package.json so `require('@stepstitch/tracker')` resolves correctly. No bundler,
// no runtime deps — just two tsc passes + this marker (matches the project's zero-dep ethos).
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
mkdirSync(join(dist, "cjs"), { recursive: true });
writeFileSync(join(dist, "cjs", "package.json"), JSON.stringify({ type: "commonjs" }, null, 2) + "\n");
console.log("finalize-dist: wrote dist/cjs/package.json (type=commonjs)");
