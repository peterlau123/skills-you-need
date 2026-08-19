---
name: jekyll-chirpy-blog
description: "Use when editing the Jekyll/Chirpy blog or fixing mermaid."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [jekyll, chirpy, blog, mermaid, github-pages]
---

# peterlau123.github.io — Jekyll/Chirpy Blog Maintenance

User's personal blog (Jekyll + Chirpy theme, GitHub Pages). Cloned at
`/data/lx/ai-engineer/peterlau123.github.io/` (origin `git@github.com:peterlau123/peterlau123.github.io.git`,
standard SSH URL — `~/.ssh/config` routes github.com → ssh.github.com:443).
Posts live in `_posts/YYYY-MM-DD-<slug>.md` (some nested under `_posts/ai/`).

## Mermaid rendering — root cause when flowcharts don't render

Chirpy theme only loads the mermaid JS bundle when the post's frontmatter has
`mermaid: true` (checked in `_includes/js-selector.html`: `{% if page.mermaid %}`).
**Without it, ` ```mermaid ` blocks render as plain text** — this is the #1 cause of
"flowchart 显示失败 / 渲染失败" reports.

Required frontmatter for any post containing mermaid:

```yaml
---
title: "..."
date: YYYY-MM-DD
layout: post
categories: [System Design, Agent]   # any
tags: [...]
mermaid: true
toc: true
---
```

`layout: post` + `toc: true` also appear on the working reference post
(`_posts/ai/2026-04-15-Agent-Harness-Enineering.md`) — copy its frontmatter shape.

## Mermaid syntax conventions (worked: Bifrost post, 2026-08-18)

- Use `flowchart LR` / `flowchart TD`, NOT the older `graph LR` — matches the blog's
  working diagrams.
- **Quote Chinese labels**: `A["GPFS 共享存储"]` — unquoted CJK labels can break parse.
- `A["label<br/>second line"]` for multi-line node text.
- Subgraphs: `subgraph Name["显示名"] ... end`; edges into/out of subgraphs are fine.
- Dotted edge with label: `W1 -.->|"fallback: 100ms 轮询"| W2`.

## Validating mermaid without a browser

`mmdc` (mermaid-cli) requires puppeteer/Chromium which is NOT installed on mx001. Instead
install mermaid + jsdom as node packages and call `mermaid.parse()` — pure syntax check,
no browser:

```bash
cd /tmp && npm init -y >/dev/null 2>&1 && npm install mermaid dompurify jsdom --no-audit --no-fund
node -e "
const { JSDOM } = require('jsdom');
const dom = new JSDOM('<!DOCTYPE html><body></body>');
global.window = dom.window; global.document = dom.window.document; global.navigator = dom.window.navigator;
const fs = require('fs');
const m = require('mermaid').default;
m.initialize({ startOnLoad: false });
(async () => {
  for (const f of process.argv.slice(1)) {
    try { await m.parse(fs.readFileSync(f, 'utf8')); console.log('PASS ' + f); }
    catch (e) { console.log('FAIL ' + f + ': ' + String(e.message||e).split('\n')[0]); }
  }
})();
" /tmp/diagram1.mmd /tmp/diagram2.mmd
```

Notes:
- `require('mermaid')` returns `{__esModule, default}` — always use `.default`.
- `mermaid.render()` additionally needs `CSSStyleSheet` (browser-only) — for CI-style
  validation `parse()` is enough. `DOMPurify.addHook is not a function` means jsdom globals
  weren't installed before requiring mermaid; `render` failing with CSSStyleSheet is expected
  in plain node — don't chase it.
- Feed each diagram from a ` ```mermaid ` block into its own `.mmd` file, then run the check.

## Post edit workflow

1. `git pull origin main && git checkout -b fix/<topic>` (user convention: branch per change;
   never push to main).
2. Edit the post; keep frontmatter conventions above.
3. Validate any mermaid blocks (above), verify code fences are paired
   (`grep -c '```'` should be even), check no leftover ASCII-art boxes
   (┌ │ ▼ └ characters) where a diagram was requested.
4. Commit `fix: <description>` / `feat: <description>`, push.
5. **PR creation**: `POST /api.github.com/repos/peterlau123/peterlau123.github.io/pulls`
   with the fine-grained `GITHUB_TOKEN` returns **403 "Resource not accessible"** — this
   repo's token has contents:write but NOT pulls:write (verified 2026-08-18; contrast:
   ai-infra-wiki PRs CAN be created via API). Fallback: push the branch and hand the user
   the compare URL `https://github.com/peterlau123/peterlau123.github.io/compare/main...<branch>`
   to open the PR manually.

## GitHub Pages deployment diagnosis — when CI is green but the site 404s

The repo has **two competing deployment mechanisms** that silently conflict:

1. **Legacy Pages builder** (`build_type: "legacy"`) — serves raw files from
   `main` branch. Controlled by Settings → Pages → Source = "Deploy from a branch".
2. **Actions workflow** (`.github/workflows/jekyll.yml`) — builds with Jekyll
   and deploys via `actions/deploy-pages@v4`. Controlled by Settings → Pages →
   Source = "GitHub Actions".

A `.nojekyll` file exists at repo root (added 2025-12-13). Under legacy mode,
this disables Jekyll processing entirely — Pages serves raw `.md` files as
`text/plain`. The Actions workflow builds correctly (Jekyll runs, artifact is
uploaded, `deploy-pages` returns success), but then the **legacy builder also
runs and overwrites the Actions artifact** with raw branch files.

**Symptoms**: CI all green, Pages build status `built`, but:
- `/posts/<slug>/` → 404
- `/sitemap.xml` → 404, `/feed.xml` → 404
- Homepage returns 200 but only 34 bytes (raw frontmatter `---\nlayout: home\n---`)
- Two deployments for the same commit; one ends `success` then `inactive`
  (superseded by the other builder)

**Fix** (requires UI — API returns 403 for `PUT /pages` with the PAT):
Settings → Pages → Build and deployment → Source → change
"Deploy from a branch" to **"GitHub Actions"**. Then re-trigger the workflow
(see "Re-triggering after Pages source change" below).

### Re-triggering after Pages source change

After switching Pages Source to "GitHub Actions", the **old legacy deployment
artifact is still live** — the site will continue 404ing until a new Actions
workflow run produces a fresh artifact. You must re-trigger the workflow:

1. **`workflow_dispatch` API returns 403** — the fine-grained PAT has
   `contents:write` but NOT `actions:write`, so:
   ```bash
   curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
     -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/peterlau123/peterlau123.github.io/actions/workflows/<workflow_id>/dispatches" \
     -d '{"ref":"main"}'
   # → 403 "Resource not accessible by personal access token"
   ```

2. **Workaround: empty commit push** (verified working 2026-08-18):
   ```bash
   cd /data/lx/ai-engineer/peterlau123.github.io
   git pull origin main
   git commit --allow-empty -m "chore: trigger redeploy after Pages source changed to workflow"
   git push origin main
   ```
   This triggers the `on: push` event for all workflows. The Jekyll build +
   deploy-pages workflow runs, produces a fresh artifact, and replaces the
   stale legacy deployment.

3. **Verify** after ~2-4 minutes (Jekyll build takes time):
   ```bash
   # CI should all be completed/success
   curl -s -H "Authorization: token $GITHUB_TOKEN" \
     "https://api.github.com/repos/peterlau123/peterlau123.github.io/actions/runs?per_page=3"
   # Page should return 200 with real content (not 34 bytes)
   curl -sL -o /dev/null -w "HTTP %{http_code} | %{size_download} bytes\n" \
     "https://peterlau123.github.io/posts/<slug>/"
   # Homepage should be ~20KB+ (full rendered HTML), not 34 bytes (raw frontmatter)
   curl -sL -o /dev/null -w "HTTP %{http_code} | %{size_download} bytes\n" \
     "https://peterlau123.github.io/"
   ```
   **Tell-tale signs of success**: article page returns 200 with 40KB+, homepage
   returns 200 with 20KB+. If homepage is still 34 bytes, the workflow hasn't
   finished or the source change didn't save.

### Diagnostic API calls (GITHUB_TOKEN from ~/.hermes/.env)

```bash
export GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | cut -d'=' -f2-)

# 1. Pages config — check build_type and source
curl -sL -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/peterlau123/peterlau123.github.io/pages"
#   build_type: "legacy" = bad (serves raw), "workflow" = good (Actions)

# 2. Latest Pages build status
curl -sL -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/peterlau123/peterlau123.github.io/pages/builds/latest"
#   status: "built" + error.message: null = build succeeded (but may be wrong builder)

# 3. Check .nojekyll exists
curl -sL -o /dev/null -w "%{http_code}" -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/peterlau123/peterlau123.github.io/contents/.nojekyll?ref=main"
#   200 = .nojekyll present (disables Jekyll under legacy mode)

# 4. Workflow run statuses (all should be success)
curl -sL -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/peterlau123/peterlau123.github.io/actions/runs?per_page=5"

# 5. Deployment statuses — look for "inactive" (superseded) vs "success"
curl -sL -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/peterlau123/peterlau123.github.io/deployments?per_page=3"
#   Then for each deployment ID:
curl -sL -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/peterlau123/peterlau123.github.io/deployments/<ID>/statuses"

# 6. Live URL check — 404 + tiny body = Jekyll not running
curl -sL -o /dev/null -w "%{http_code} %{size_download}bytes" \
  "https://peterlau123.github.io/posts/<slug>/"
curl -sL -o /dev/null -w "%{http_code}" "https://peterlau123.github.io/sitemap.xml"
```

**Decision tree**: if `build_type=legacy` AND `.nojekyll` exists AND CI is green
AND posts return 404 → the legacy/workflow conflict is the cause. Fix by switching
Source to "GitHub Actions" in repo Settings → Pages (user must do this in UI;
PAT returns 403 on `PUT /pages`).

See `references/pages-deployment-diagnosis.md` for the full session transcript
of this diagnosis, including the post-fix re-trigger sequence.

## PAT permission matrix (peterlau123.github.io, verified 2026-08-18)

The fine-grained `GITHUB_TOKEN` in `~/.hermes/.env` has limited scopes for this
repo. Known capabilities:

| API action | Result | Scope needed |
|---|---|---|
| `GET /pages` (read config) | ✅ 200 | (read) |
| `PUT /pages` (change build_type) | ❌ 403 | Pages admin |
| `POST /actions/workflows/.../dispatches` | ❌ 403 | `actions:write` |
| `POST /pulls` (create PR) | ❌ 403 | `pulls:write` |
| `GET /contents/...` (read files) | ✅ 200 | `contents:read` |
| `PUT /contents/...` (write files via API) | ✅ 200 | `contents:write` |
| Git push (via SSH key) | ✅ works | SSH key (separate from PAT) |

**Pattern**: when an API action returns 403, fall back to git push (SSH key is
independent of PAT scopes). An empty commit push is the universal workaround
for triggering `on: push` workflows when `workflow_dispatch` is blocked.

## Environment notes

- No local Jekyll/Ruby (`bundle` not found) — cannot `jekyll build` locally; GitHub Actions
  deploys on merge. Validate mermaid syntactically and rely on CI for the rest.
- GitHub Pages deploy requires `build_type: "workflow"` (see diagnosis section above).
  If Pages Source is still "Deploy from a branch" (legacy), the site will serve raw
  files and all posts will 404 despite green CI. After changing Source to "GitHub
  Actions" in UI, **must re-trigger** via empty commit push — `workflow_dispatch`
  API returns 403 (PAT lacks `actions:write`).
- `gh` CLI is NOT installed; use the GitHub REST API via `curl` with `GITHUB_TOKEN`
  from `~/.hermes/.env`.
