# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **Home Assistant custom integration** for Aseko pool units (ASIN AQUA). It is the
**first-party, Aseko-built integration** — the user/maintainer works at Aseko. Two
other Aseko integrations exist and should not be confused with this one:

- `aseko_pool_live` — ships inside `home-assistant/core`, but **third-party**,
  reverse-engineered by `@milanmeu` (the user's company considers this "a pain").
- `home-assistant-aseko-local` (`hopkins-tk` / `Enrica-r` on GitHub) — HACS,
  unofficial, MITM of the device's local TCP stream.

This repo's eventual goal is to replace `aseko_pool_live` in HA core.

## Which API this targets — and which it must NOT

There are two Aseko clouds:

| Host | Use |
|---|---|
| `https://api.aseko.cloud/api/v1` — **public integrator API** | ✅ what this integration uses |
| `*.acs.aseko.cloud` (REST `/auth/*` + GraphQL) — **internal mobile-app backend** | ❌ production explicitly returns `403 — "If you are integrator, use official integrator API"` |

**Do not pivot this integration back to the `acs` API** without explicit user
direction. Production blocks it for integrators, and the `acs` GraphQL
`StatusValue` returns display-formatted strings instead of typed numbers — the
integrator API is both allowed and cleaner.

The integrator API has only 3 endpoints (`/auth/check`, `/paired-units`,
`/paired-units/{serial}`), all GET. There is **no push, no control, no account
id, no firmware field** — these gaps are tracked in README "Open items".

## High-level architecture

```
config_flow.py  ─►  api.AsekoCloudApi  ─►  coordinator  ─►  entry.runtime_data
                          (REST polling)            ▲
                                                    │
                                       sensor.py & binary_sensor.py
                                            (read coordinator.data)
```

Non-obvious things that span multiple files:

- **`api.py` deliberately has zero Home Assistant imports.** It must stay
  self-contained so it can be extracted to a PyPI package when this integration
  is submitted to HA core (which requires API code outside `homeassistant/`).
- **Entities are descriptions, not classes.** `sensor.STATUS_SENSORS` and
  `binary_sensor.BINARY_SENSORS` are dataclass descriptions keyed off **raw API
  JSON field names** (`api_field="waterTemperature"`, not a parsed dataclass
  attribute). The API JSON *is* the data model — `AsekoUnit.status_values` is
  stored as a plain dict.
- **Entities are created only when the unit reports the field**
  (`description.api_field in unit.status_values`). Not every unit has every
  sensor — the same code adapts to ASIN AQUA Pro / Salt / Oxygen / Profi.
- **Enum sensors lowercase API values** (`"AUTO"` → `"auto"`) to match the
  `options=[...]` list and HA's state-translation keys.
- **`cl_free_required` has a dynamic unit** — the unit comes from the API's
  `clFreeRequiredUnit` field via the description's `unit_field`. This is the
  only sensor whose `native_unit_of_measurement` is computed at runtime; see the
  property override in `sensor.py`.
- **Config-entry `unique_id` is a SHA-256 hash of the API key.** The integrator
  API returns no account identifier (this is on the README roadmap to fix
  server-side). Reauth *deliberately* does not re-check unique_id — a new key
  has a different hash, and re-checking would block legitimate reauth.
- **Platform pre-import in `__init__.py`** via
  `homeassistant.helpers.importlib.async_import_module` is mandatory before
  `async_forward_entry_setups`. Without it HA logs a blocking-event-loop
  warning for custom integrations. Do not remove the `asyncio.gather(...)` at
  the top of `async_setup_entry`.
- **API keys expire.** `/auth/check` returns `expiresAt`; an expired key
  produces HTTP 401 with `errorType: API_KEY_EXPIRED`. The coordinator catches
  the resulting `AsekoAuthError` and raises `ConfigEntryAuthFailed`, which
  triggers HA's reauth dialog. Validated in practice — the initial test key
  expired and the reauth path fired correctly. If a user reports "stopped
  working", check key expiry first.

## Translations and entity IDs

Three files must stay in sync when entities change:

- `strings.json` — translation source-of-truth (also what hassfest reads when
  submitting to HA core)
- `translations/en.json` — runtime English
- `translations/cs.json` — runtime Czech (Aseko is a Czech company)

**Entity IDs are generated from the *translated* name.** On a Czech HA install
entities look like `binary_sensor.my_new_unit_filtrace` (not `_filtration`),
`sensor.my_new_unit_volny_chlor` (not `_cl_free`), etc. The dashboard YAML in
chat history assumes Czech IDs. The internal `translation_key` (e.g.
`cl_free`) is what's stable across locales.

## Common edits

| Change | Edit |
|---|---|
| Add a metric the API already returns | `STATUS_SENSORS` in `sensor.py` (matching `api_field` from `StatusValues` schema) + entry in all 3 translation files |
| Add a boolean state | `BINARY_SENSORS` in `binary_sensor.py` (with `_status_value(...)`, `_has_status_value(...)`) + translations |
| Rename / restructure an API field | only `api.py` plus the `api_field=` strings in sensor.py / binary_sensor.py |
| Cut a new release | bump three things together: `manifest.json` `version`, `const.CLIENT_VERSION`, the git tag (`gh release create vX.Y.Z --generate-notes`). HACS installs the latest tag — `main` alone won't reach users. |

## Local testing

There is no test suite. Verification is end-to-end against a real HA running
in Docker, plus syntax/JSON checks.

```bash
# Syntax check (catches the TypeError-class of bugs)
python3 -m py_compile custom_components/aseko_cloud/*.py

# JSON validation for every JSON file
for f in $(find custom_components hacs.json -name '*.json'); do
  python3 -c "import json; json.load(open('$f'))" && echo "OK: $f"
done

# Local Home Assistant in Docker, with the integration live-mounted
docker run -d --name homeassistant --restart=unless-stopped \
  -e TZ=Europe/Prague \
  -v ~/ha-test-config:/config \
  -v "$(pwd)/custom_components/aseko_cloud:/config/custom_components/aseko_cloud" \
  -p 8123:8123 \
  ghcr.io/home-assistant/home-assistant:stable
# HA UI: http://localhost:8123  (LAN IP for phone testing: `ipconfig getifaddr en0`)

# After editing any integration file:
docker restart homeassistant

# Watch logs (filter to our integration + errors):
docker logs -f homeassistant 2>&1 | grep -iE 'aseko|error|traceback'

# Inspect what HA created (config entry, entity registry):
python3 -c "import json; print(json.load(open('$HOME/ha-test-config/.storage/core.entity_registry'))['data']['entities'][:3])"
```

The blocking Docker container is named `homeassistant`. Config persists in
n`~/ha-test-config/` even after `docker rm -f homeassistant`. **HACS 2.0.5 is
installed in this test instance** (real dir at
`~/ha-test-config/custom_components/hacs`, not a mount) so the HACS install flow
can be reproduced locally; `aseko_cloud` is the live mount.

### Headless verification (no browser)

You can confirm the integration is registered server-side without clicking
through the UI. Mint a short-lived access token from the stored refresh token
(HA signs access JWTs HS256 with the refresh token's `jwt_key`, payload
`{iss: <refresh_token_id>, iat, exp}`), reading `~/ha-test-config/.storage/auth`:

- **Pick an *owner* user's `normal` refresh token** — the config-entries flow
  API is admin-only, so a `system` token (e.g. "Home Assistant Content")
  returns `401` even though `GET /api/` works with it.
- **Is the config flow registered / functional?**
  `POST /api/config/config_entries/flow` with `{"handler":"aseko_cloud"}` — a
  registered flow returns a `type:"form"` with the `api_key` field; an unknown
  handler errors. (This leaves an in-progress flow that creates *no* config
  entry and is discarded — safe.)
- **Is it in the Add-Integration picker list?** Connect to
  `ws://localhost:8123/api/websocket` (auth handshake, then `manifest/list`) and
  check for `domain=aseko_cloud, config_flow=True, is_built_in=False`. Use the
  repo's `.venv/bin/python` (has `aiohttp`). `manifest/list` only returns
  loaded/scanned integrations, so the core `aseko_pool_live` may be absent — that
  does not affect ours.

## Things HA reviewers will check before core submission

Tracked in README roadmap. The three blockers specifically are:

1. `api.py` must move to a separate PyPI package referenced from
   `manifest.json` `requirements`. It is already structured for this (no HA
   imports, only `aiohttp` + stdlib).
2. A test suite under `tests/components/aseko_cloud/` mocking `aiohttp`.
3. Config-entry diagnostics (`diagnostics.py`).

## Repository & distribution

- Repo: <https://github.com/dkk54/ha-aseko-cloud>
- License: Apache-2.0
- `codeowners` in `manifest.json`: `@dkk54`
- Latest release: **v0.1.1** — also pinned in `manifest.json` `version` and
  `const.CLIENT_VERSION` (sent in `X-Client-Version` header). Keep all three in
  sync on every release.
- HACS + hassfest validation runs in `.github/workflows/validate.yml` on every
  push / PR and nightly. Nightly is the early-warning canary for upstream
  HA or HACS changes that break our manifest.
- Brand assets ship **inside the integration** at
  `custom_components/aseko_cloud/brand/{icon,dark_icon,logo,dark_logo}.png`
  (HA 2026.3+ convention — `home-assistant/brands` no longer accepts custom
  integration brands; see
  <https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api>).
  These take priority over the brands CDN automatically.

### How users install it today

| Path | Available |
|---|---|
| **HACS default catalog** (search "Aseko Cloud" in HACS) | ⏳ pending <https://github.com/hacs/default/pull/7991> — all 11 automated checks ✅, waiting for a human HACS maintainer review. HACS docs say "reviews take months." Don't nudge before ~4–6 weeks of silence. |
| **HACS custom repository** (paste the repo URL) | ✅ works today |
| **Manual** (copy `custom_components/aseko_cloud/` into HA `config/`) | ✅ works today |

The default-catalog merge only adds *discoverability* — anyone willing to add
a custom repository can install today.

### Common install confusion (support triage)

A custom integration appears in HA's **Add Integration** picker **only after its
files are on disk in `config/custom_components/` and HA has been restarted** —
the picker does not download custom integrations. So the usual support chain is:

1. *"Can only use HACS integrations / can't find it in HACS"* → it is **not in
   the HACS default store yet** (PR #7991 pending). Direct users to **HACS → ⋮ →
   Custom repositories**, URL `https://github.com/dkk54/ha-aseko-cloud`, type
   **Integration**, then download → **restart** → Add Integration. (Or copy the
   folder in manually.) This is the #1 user report and is **not a bug**.
2. *"Installed it but it's not in Add Integration"* → they skipped the
   **restart**, or it's a stale **frontend cache** — a hard refresh
   (Cmd/Ctrl+Shift+R) or a private window fixes it. Verified the picker shows
   *zero* even for the core `aseko_pool_live` when the cache is stale.
3. Czech UI: *Nastavení → Zařízení a služby → Přidat integraci*; the entity to
   pick is **Aseko Cloud** (custom badge, asks for an **API key**) — **not**
   "Aseko Pool" (core `aseko_pool_live`, asks for email/password).

The server side being correct is provable headlessly (see *Headless
verification* under Local testing) — reach for that before assuming an
integration bug when a user "can't find" it.
