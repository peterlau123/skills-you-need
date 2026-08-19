---
name: hermes-custom-provider
description: "Use when adding custom LLM providers to Hermes."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [hermes, provider, openai-compatible, plugin, config]
---

# Adding a Custom OpenAI-Compatible Provider to Hermes

Use when the user gives you a custom LLM endpoint ("add provider", base URL + API key, e.g. an
internal MaaS gateway like yicloud) and wants Hermes to use it — as a test switch, a new default,
or a fallback. Verified end-to-end on mx001 2026-08-05 with yicloud (`https://maas.yicloud.com/v1`).

## Steps

1. **Store the API key in `.env` FIRST** (never config.yaml — secrets belong in the profile's
   `.env`). Append with terminal `printf '%s\n' 'NAME_API_KEY=<key>' >> ~/.hermes/profiles/<profile>/.env`.
   Then always source it, never embed the literal in commands:
   `export NAME_API_KEY=$(grep '^NAME_API_KEY=' ~/.hermes/profiles/<profile>/.env | cut -d= -f2)`
2. **Verify the endpoint directly with curl before touching Hermes config**:
   - List models: `curl -s -H "Authorization: Bearer $KEY" <base>/models` → confirms auth AND gives
     the exact model ids (don't guess — e.g. yicloud exposes `glm5.2`, `glm5.2-pd`, `glm4.7`, `kimi-k3`).
   - Chat test: `POST <base>/chat/completions` with `{"model":"<id>","messages":[...],"max_tokens":300}`.
     Note: reasoning models (glm5.2) eat `max_tokens` on thinking — a 20-token cap returns empty
     `content` with nonzero `reasoning_tokens`; use ≥200 to see real text.
3. **Create the user provider plugin** (this is the pattern the shipped providers use):
   `~/.hermes/profiles/<profile>/plugins/model-providers/<name>/__init__.py`:
   ```python
   from providers import register_provider
   from providers.base import ProviderProfile

   <name> = ProviderProfile(
       name="<name>",
       aliases=("<name>-maas",),
       display_name="<Name> MaaS",
       description="...",
       env_vars=("<NAME>_API_KEY",),
       base_url="https://<host>/v1",
       auth_type="api_key",
       default_aux_model="<a cheap chat model id>",
       fallback_models=("<id2>", "<id3>"),
   )
   register_provider(<name>)
   ```
   plus a sibling `plugin.yaml`:
   ```yaml
   name: <name>-provider
   kind: model-provider
   version: 1.0.0
   description: ...
   ```
4. **Enable the plugin**: `hermes plugins list | grep <name>` → shows `not enabled`; then
   `hermes plugins enable <name>-provider`. A "may not override built-in tools" warning is benign.
5. **Test through Hermes** (explicit override, before changing defaults):
   `hermes chat -q "<prompt>" -m <model-id> --provider <name>` — confirm the response text.
6. **Switch the default only after the test passes**:
   `hermes config set model.provider <name>` and `hermes config set model.default <model-id>`.
   Verify with `hermes config get model`; final check: `hermes chat -q "回复OK即可"` with no overrides.

## Pitfalls

- Config changes affect NEW sessions only — the current live conversation keeps its old model.
  Tell the user; switching the live session needs a gateway restart or `/model`.
- **config.yaml can be silently reverted by an external actor** (observed on mx001 2026-08-06: the
  default was set to yicloud/glm5.2 and verified, but hours later `hermes config get model` showed
  deepseek again — another session/tool had overwritten the file). The RUNNING gateway keeps the
  config it started with, so the live session may still show the new model while the file says
  otherwise. When verifying later, be explicit: `hermes config get model -p <profile>` (the CLI
  default profile may differ from the live session's), and distinguish "file state" from "live
  session state" — check BOTH before claiming the switch stuck.
- The user-plugin dir is per-profile: `plugins/model-providers/<name>/` under the ACTIVE profile's
  home (resolve via `$HERMES_HOME`), not the bundled repo's `plugins/`.
- ProviderProfile fields that matter: `env_vars` (which .env var carries the key), `base_url`,
  `auth_type="api_key"`, `default_aux_model` (aux/vision model — pick a cheap id from the /models
  list to avoid resolution failures).
- After adding a provider, configure a fallback so the new default has a fallback chain
  (single-provider setups break on provider outages). See "Fallback configuration" below.
- If the user says "switch to model X" but X has no exact id, list `/v1/models` and match by
  substring (e.g. "glm 5.2" → `glm5.2`).

## Fallback configuration

`hermes fallback add` is an **interactive picker only** — it does NOT accept provider/model
arguments on the CLI (`hermes fallback add deepseek` → error). Two ways to configure:

**Option A (preferred): edit config.yaml directly.** Add a **top-level** `fallback_providers` key
(NOT under `model:`, NOT `model.fallbacks` — that key is ignored):

```yaml
fallback_providers:
  - provider: deepseek
    model: deepseek-chat
```

Write it with Python+PyYAML (preserves existing structure), then verify:
```bash
hermes fallback list   # should show: Primary + Fallback chain
```

**Option B: `hermes fallback` (no args)** launches the interactive picker — works but not
scriptable.

### Fallback pitfalls (observed 2026-08-06)

- `hermes config set model.fallbacks '[{...}]'` writes to `model.fallbacks` — **wrong key**,
  silently ignored by `hermes fallback list`. The correct key is top-level `fallback_providers`.
- `hermes config set` with `--delete` flag → `unrecognized arguments` (no such flag exists).
  Use `sed -i` or PyYAML to remove unwanted keys from config.yaml.
- Each fallback entry needs BOTH `provider` and `model` — entries missing either are ignored.
- `fallback_model` (singular) is the legacy key, still honored for back-compat, but
  `fallback_providers` (plural list) takes priority. Use the plural form.

## Provider self-check (run after setup or when asked to verify)

Systematic check that all configured providers actually work:

1. **Config state vs live state** — `hermes config get model -p <profile>` reads the file;
   the running gateway may differ (config can be silently reverted — see Pitfalls above).
   Check BOTH file content (`grep -A2 "^model:" config.yaml`) and what the live session reports.
2. **Per-model curl test** — for each model on each provider, send a minimal chat request:
   ```bash
   curl -s --max-time 30 -X POST "<base>/chat/completions" \
     -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"model":"<id>","messages":[{"role":"user","content":"回复OK"}],"max_tokens":100}' \
     | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('choices',[{}])[0].get('message',{}); print('✅' if c else '❌', (c.get('content') or json.dumps(d,ensure_ascii=False))[:80])"
   ```
3. **Listed ≠ callable** — models in `/v1/models` may return "Invalid model name" on actual
   calls (observed: yicloud `glm5.2-pd` listed but errors). Test with a real chat request, not
   just the models endpoint.
4. **Reasoning models** — glm4.7, kimi-k3, and glm5.2 (at low max_tokens) return empty `content`
   with nonzero `reasoning_tokens`. Use `max_tokens ≥ 200` and check `reasoning_content` field
   to distinguish "broken" from "thinking too much."
5. **Fallback chain** — `hermes fallback list` should show Primary + fallback entries. If empty,
   the fallback key is wrong (see pitfalls above).
