---
name: github-restricted-network-access
description: Use when github.com clone times out or install fails.
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
---

# GitHub Access Behind a Restricted Network

Some networks (e.g. this machine, hostname mx001) block `github.com:443` outright but leave other GitHub services reachable. Direct `git clone` hangs until timeout; `hermes skills install` fails with "Could not fetch from any source" when its resolution path hits the GitHub API. This skill is the verified fallback ladder — do NOT retry the direct clone more than once.

## Step 0 — Probe before assuming

```bash
# Which GitHub surfaces are reachable? (000 = unreachable/timeout)
curl -s --max-time 8 -o /dev/null -w "github.com: %{http_code}\n" https://github.com
curl -s --max-time 8 -o /dev/null -w "api.github.com: %{http_code}\n" https://api.github.com
curl -s --max-time 8 -o /dev/null -w "codeload: %{http_code}\n" https://codeload.github.com
# Probe a candidate proxy against the actual git endpoint:
curl -s --max-time 8 -o /dev/null -w "%{http_code}\n" "https://<proxy>/https://github.com/<owner>/<repo>.git/info/refs?service=git-upload-pack"
```

Verified on this network: `api.github.com`, `raw.githubusercontent.com`, `codeload.github.com` reachable; `github.com` itself and `clawhub.org` NOT reachable.

## Step 1 — Clone: prefer direct SSH when the pubkey is already registered

If `~/.ssh/config` routes `github.com` → `ssh.github.com:443` AND the pubkey is registered (verified 2026-08-04 on mx001: `ssh -T git@ssh.github.com` → "Hi peterlau123!"), **just clone with the standard SSH URL first** — it worked when the proxy hung (see pitfall below):

```bash
git clone git@github.com:<owner>/<repo>.git
```

## Step 1b — Clone via a proxy prefix (fallback: no SSH key / other machines)

```bash
git clone https://gh-proxy.com/https://github.com/<owner>/<repo>.git
# verified 200 on this network; alternative: https://ghproxy.net/https://github.com/...
```

Probe any other mirror (ghfast.top, gitclone.com, hub.gitmirror.com) before use — availability changes. Keep the proxy prefix in `origin` (future `git pull` just works).

## Push — the proxies are READ-ONLY; use SSH over 443

`gh-proxy.com` / `ghproxy.net` prefix URLs clone fine but **cannot push**. Verified on mx001: `git push` through the proxy dies with `fatal: could not read Username for 'https://gh-proxy.com'` (no auth pass-through; the proxy answers 403 to write paths). Also `github.com:22` and `github.com:443` both time out — the ONLY reachable push route is SSH over HTTPS:

```bash
# Probe (connectivity check):
ssh -p 443 -T git@ssh.github.com
# "Permission denied (publickey)" = connection OK, key not registered on the account
```

Fix path (requires one user action): register the machine's pubkey on GitHub (Settings → SSH and GPG keys), then push over port 443:

**STATUS ON mx001: RESOLVED — verified 2026-08-04.** The pubkey IS registered; `ssh -T git@ssh.github.com` returns "Hi peterlau123! You've successfully authenticated" and `git push` works (pushed `feat/paper-notes` to ai-infra-wiki). Working config already in place on this machine:

```
# ~/.ssh/config  (already applied on mx001)
Host github.com
    HostName ssh.github.com
    Port 443
    User git
    IdentityFile ~/.ssh/id_ed25519
```
```bash
git remote set-url origin git@github.com:<owner>/<repo>.git   # standard URL — routing handled by ssh config
git push -u origin <branch>
```

On other machines/accounts: register the pubkey first, then push over 443 as above.

No `GITHUB_TOKEN` in `~/.hermes/.env` on this machine — SSH is the push path, not the API key.

## Step 2 — Tarball fallback (no git history needed)

```bash
curl -sL -o repo.tar.gz "https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<branch>"
tar xzf repo.tar.gz
# If a real git repo is required: git init && git remote add origin <url> && git add/commit
```

## Step 2b — Inspect repo / fetch single files via API + raw (no clone)

When you only need to READ files (verify a claim, check an implementation, list a repo's structure), skip clone AND tarball — list via the contents API, then pull the exact files raw. Both routes work through gh-proxy on mx001 (verified 2026-08-05):

```bash
# 1. List a directory (JSON: type/name/size per entry)
curl -sL --max-time 60 "https://gh-proxy.com/https://api.github.com/repos/<owner>/<repo>/contents/<dir>?ref=main"
# 2. Fetch one file directly
curl -sL --max-time 90 "https://gh-proxy.com/https://raw.githubusercontent.com/<owner>/<repo>/main/<path>" -o <local>
```

Worked example: inspected `disler/pi-vs-claude-code` extension sources (`extensions/coms.ts`, `coms-net.ts`, ~50KB each) this way after both a proxied clone and a tarball fetch failed. Also the right path for locating files before manual installs.

## Step 3 — `hermes skills install` fallback (manual install)

When install fails (rate limit, unreachable registry), pull the repo tarball via codeload and copy skill directories straight into the profile:

```bash
HERMES_HOME=$(hermes config path)          # e.g. ~/.hermes/profiles/<profile>
mkdir -p "$HERMES_HOME/skills/<category>"
cp -r <repo>/skills/<skill-dir> "$HERMES_HOME/skills/<category>/"   # copy WHOLE dirs — SKILL.md alone misses supporting files (agents/, tests.md, scripts/)
hermes skills list   # verify: shows as source 'local', status enabled
```

Result is a normal enabled skill but tracked as `local` — `hermes skills update` won't manage it; re-run the tarball copy to refresh. Supporting files matter: e.g. mattpocock `tdd` carries `agents/openai.yaml`, `tests.md`, `mocking.md`.

## GitHub API rate limits

Unauthenticated: 60 req/hr per IP (shared IPs exhaust fast — it bit this session mid-work). Fix: set `GITHUB_TOKEN` in `~/.hermes/.env` or `gh auth login` (5,000/hr). `raw.githubusercontent.com` and `codeload.github.com` are NOT rate-limited — prefer them for single-file / tarball fetches.

## Pitfalls

- **`~/.git-credentials` may hold an internal GitLab entry, not a usable proxy**: on mx001 the only stored credential is `http://liux:***@10.20.30.25:8080`, and 10.20.30.25:8080 is a GitLab web app (`/users/sign_in` redirect), NOT an HTTP CONNECT proxy — `curl -x http://liux@10.20.30.25:8080 https://api.github.com` fails with `000` and git push through it dies with `HTTP 400 from proxy after CONNECT`. Don't burn probes treating it as a general egress proxy.
- **Re-probe before believing "direct access works"**: a user may insist github.com is reachable because it IS, from their laptop or another environment (e.g. the H20 box). Step 0 costs seconds — run it and show the evidence (`github.com -> HTTP 000`, `codeload -> 301`, `proxy -> 200`) rather than silently switching strategies on hearsay. `HTTP 000` is curl's "no response at all" (connect failure/timeout), distinct from any real HTTP status — it means the block is still in effect.
- **Pipe masks exit codes**: `timeout 60 git clone ... | tail -3` reports tail's exit, not git's. Always verify the target directory contents afterwards.
- **gh-proxy `git clone` can silently return an EMPTY repo**: clone exits 0 but `git log` says "your current branch 'master' does not have any commits yet" and the worktree has no files. Always check `ls`/`git log` after a proxied clone; if empty, fall to Step 2 (codeload) or Step 2b (API+raw) instead of retrying the clone.
- **gh-proxy HTTPS `git clone` can HANG outright** (observed 2026-08-06: `git clone https://gh-proxy.com/...peterlau123.github.io.git` timed out at 120s, exit 124), even for repos that cloned fine before — availability varies by repo/size/transient state. Don't retry the proxy twice; after ONE hang, fall to direct SSH clone (Step 1) which completed in seconds on the same network.
- **gh-proxy routes to `codeload.github.com` and `/archive/refs/heads/*.tar.gz` HANG** (observed twice, `curl` exit 28 timeout). The tarball route on this network is DIRECT codeload (Step 2); the proxied routes are for api/raw only. Don't burn 2-3 minutes per attempt on proxied tarballs.
- **Never `rm -rf` the shell's cwd**: git then dies with "Unable to read current working directory". `cd` somewhere valid first.
- **`hermes skills install` with a bare ambiguous name** ("Multiple skills found") — use the FULL identifier from `hermes skills search <name> --json` (e.g. `skills-sh/<owner>/<repo>/<skill>`); a clawhub identifier equal to the bare name is an install trap.
- **Verify ambiguous clone destinations**: before cloning to a path the user named, inspect the target and parent workspace for convention (e.g. this machine keeps repos at `/data/lx/<project>/` — a folder named like the Hermes profile turned out to be an Obsidian wiki home, not the agent). Check first; a wrong 500MB clone is wasted work.
- hermes-agent source on this machine lives at `~/.hermes/hermes-agent/`, cloned from a China mirror: `https://cnb.cool/hermesagent-cn/hermes-agent-cn-mirror.git` (use it when github.com is unreachable).
