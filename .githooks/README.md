# Git hooks (optional)

One hook, opt-in, and it only runs the same lint and type checks CI runs.

| Hook | What it does |
|------|--------------|
| `pre-push` | Runs the root type-check, plus `web/` lint + type-check when `web/` changed. Skips loudly rather than blocking when a toolchain is missing. Vitest stays in CI. |

## Enable it

```bash
npm run hooks:install
```

That is `git config core.hooksPath .githooks` — local to your clone, and reversible with
`git config --unset core.hooksPath`. Nothing installs it for you: `npm install` builds the
package and does not touch your git configuration.

To bypass it once: `git push --no-verify`.

## What this hook deliberately does not check

**Identity.** It has no opinion about your name, your email, or the trailers in your commit
messages. An earlier version of these hooks enforced a single maintainer's identity on every
commit — which meant anyone who cloned the repository and ran `npm install` got a hook that
rejected their own work. Attribution policy belongs in your own global git configuration,
not in a repository other people contribute to.
