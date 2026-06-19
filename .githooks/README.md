# Git hooks (committed)

These hooks keep the history attributed to **CyKiller &lt;cykiller@msn.com&gt;** only.

| Hook | What it does |
|------|--------------|
| `commit-msg` | Strips any `Co-Authored-By: Claude …` / "Generated with …" trailers from each commit message automatically. |
| `pre-push`   | Refuses to push commits whose author **or** committer isn't `CyKiller <cykiller@msn.com>`, or that still carry an AI trailer. |

## One-time setup per clone

Hooks in a committed directory aren't active until you point git at them:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/*
```

## Local identity (also recommended)

```bash
git config user.name  "CyKiller"
git config user.email "cykiller@msn.com"
```
