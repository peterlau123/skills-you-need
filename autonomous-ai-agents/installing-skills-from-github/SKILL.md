---
name: installing-skills-from-github
description: "Install & publish GitHub skills; codeload tarball fallback."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [skills, hermes, github, install, codeload, rate-limit, workaround]
---

# Installing Skills from GitHub Repos

Use when asked to install skills ("install X skill", "装个 skill") that come from GitHub
repositories or skill registries (skills.sh, clawhub), and when `hermes skills install` fails
on network reachability or GitHub API rate limits.

## Normal path (hub install)

1. Discover identifiers:
   - `hermes skills search <name>` — table view; add `--source <src> --json` for clean full
     identifiers (scripting-friendly). `--source` accepts e.g. `clawhub`, `skills-sh`.
   - `hermes skills inspect <identifier>` — preview a skill before installing.
2. Install: `hermes skills install <full-identifier> -y` (`-y` skips the confirmation prompt).
3. Verify: `hermes skills list` (source column shows where it came from).

Pitfall: bare names are ambiguous when multiple registries host them (e.g. `ponytail` exists on
both clawhub and skills.sh). The CLI refuses with "Multiple skills found — use the full
identifier". ClawHub's full identifier IS the bare name (a naming collision), so if the bare name
won't resolve, use the skills.sh variant `skills-sh/<owner>/<repo>/<skill>` instead.

## Fallback path (tarball — bypasses GitHub API and github.com)

When install fails with "Could not fetch ... from any source" plus "GitHub API rate limit
exhausted" (unauthenticated limit is 60 req/hr per IP; shared IPs exhaust it fast), or when
github.com:443 times out:

1. Download the repo tarball. **codeload.github.com is a separate endpoint from github.com and
   api.github.com — it typically still works when both of those fail**:
   ```bash
   curl -sL -o repo.tar.gz "https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<branch>"
   tar xzf repo.tar.gz
   ```
   Branch is usually `main`; try `master` if 404. Sanity-check: `tar tzf repo.tar.gz | head`.
2. Locate the skills: `find <extracted> -name SKILL.md`.
3. Copy WHOLE skill directories — SKILL.md plus supporting files (`agents/`, sibling `*.md`,
   `scripts/`, `references/`). Many skills reference sibling files and break if copied alone:
   ```bash
   cp -r <extracted>/skills/<name> "$HERMES_HOME/skills/<category>/<name>"
   ```
   Resolve `$HERMES_HOME` (e.g. `/home/<user>/.hermes/profiles/<profile>`) — never hardcode `~/.hermes`.
4. Verify: `hermes skills list` — installed skills show source=`local`, status `enabled`.

## Resolving fuzzy skill names

If the requested name is not a real skill (e.g. "mattpock" → Matt Pocock), resolve it via the
GitHub search API (api.github.com works even when github.com itself is blocked, until rate-limited):
```bash
curl -s "https://api.github.com/search/repositories?q=<query>"
curl -s "https://api.github.com/repos/<owner>/<repo>/contents/skills"   # list skill dirs
```

## Pitfalls

- Locally-copied skills show source=`local`; `hermes skills update` / `hermes skills check` will
  NOT update them — re-copy from the repo to refresh.
- `hermes skills tap add <repo>` registers a source, but `hermes skills search` has NO `--tap`
  flag, and installs from taps still resolve through skills.sh → GitHub API. The tap alone does
  not dodge rate limits.
- Copy the whole skill directory, not just SKILL.md (see step 3 above).
- `hermes skills install` also accepts a direct `https://…/SKILL.md` URL, but prefer the tarball
  copy when the skill has sibling files you can't enumerate.
- Clean up the tarball and extracted dirs after installing.
- Deleting extracted temp dirs under /tmp triggers a "delete in root path" approval — expected, not an error.

## Publishing skills to a personal GitHub repo

Use when the user asks to "提交 skill" / "传到仓库" / "publish" a locally-developed skill to
their personal GitHub skills repo (e.g. `peterlau123/skills-you-need`). This is the reverse
direction of install — pushing local skills *up* to a repo for sharing/backup.

### Workflow

1. **Locate the source skill** in the active profile:
   ```
   ~/.hermes/profiles/<profile>/skills/<category>/<name>/
   ```
   The skill may also exist in the Hermes source repo (`/data/lx/ai-engineer/hermes-agent/skills/`)
   if it's a bundled skill with local modifications — diff against the active profile copy to
   ensure you publish the right version.

2. **Determine the category directory.** The repo should mirror Hermes's category structure:
   `productivity/`, `software-development/`, `mlops/`, etc. The user cares about proper
   classification ("注意将skill进行分类") — match the category from the local skill path.

3. **Copy the WHOLE skill directory** — SKILL.md plus all subdirs (`references/`, `scripts/`,
   `templates/`). Do NOT copy README.md from the source repo (it belongs to the source, not the
   skill). Keep LICENSE if present.

4. **Maintain a repo-level README.md** with a skills index table:
   ```markdown
   | Category | Skill | Description |
   |----------|-------|-------------|
   | productivity | ocr-and-documents v2.4.0 | ... |
   | software-development | philosophy-of-software-design | ... |
   ```
   Append a row for each new skill.

5. **Commit and push**:
   ```bash
   git add -A
   git commit -m "feat: add <skill-name> [<version>]\n\n<bullet summary of key changes>"
   git push
   ```

### Pitfalls

- **Fine-grained PAT cannot delete repos.** Deleting a GitHub repo requires `administration:write`
  scope on the PAT. Fine-grained PATs used for skill installs (contents:write) lack this.
  Tell the user to delete via the GitHub web UI (Settings → Danger Zone → Delete this repository).
  Do NOT present this as a "tool doesn't work" — it's a scope limitation, not a broken tool.
- **Always diff the active profile copy against the repo copy** before committing — the profile
  copy may have local edits that the repo copy doesn't.
- **Migrating a skill from a standalone repo to the skills collection:** copy all files including
  `references/`, update the README index, then the user can delete the standalone repo.
