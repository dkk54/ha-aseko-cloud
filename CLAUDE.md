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
| Promote staging URL → production | `STAGING` toggle and URL constants in `const.py` — but for the integrator API there is currently *only* production; staging URLs there are placeholders |

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
`~/ha-test-config/` even after `docker rm -f homeassistant`.

## Things HA reviewers will check before core submission

Tracked in README roadmap. The three blockers specifically are:

1. `api.py` must move to a separate PyPI package referenced from
   `manifest.json` `requirements`. It is already structured for this (no HA
   imports, only `aiohttp` + stdlib).
2. A test suite under `tests/components/aseko_cloud/` mocking `aiohttp`.
3. Config-entry diagnostics (`diagnostics.py`).

## Repository & releases

- Repo: <https://github.com/dkk54/ha-aseko-cloud>
- License: Apache-2.0
- `codeowners` in `manifest.json`: `@dkk54`
- HACS + hassfest validation runs in `.github/workflows/validate.yml` on every
  push / PR and nightly
- Releases are cut via `gh release create vX.Y.Z --generate-notes` — HACS
  installs the latest tagged release (not `main`), so a new tag is required
  for users to pick up changes
- Brand assets ship **inside the integration** at
  `custom_components/aseko_cloud/brand/{icon,dark_icon,logo,dark_logo}.png`
  (HA 2026.3+ convention — `home-assistant/brands` no longer accepts custom
  integration brands; see
  <https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api>).
  These take priority over the brands CDN automatically.
