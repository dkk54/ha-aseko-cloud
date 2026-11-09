# Contributing

## Architecture

```
custom_components/aseko_cloud/
  __init__.py        Config entry setup; serves the pool dashboard
  manifest.json      Integration metadata (cloud_polling)
  const.py           Constants and API URLs
  api.py             Aseko integrator API client + data model (no HA imports)
  coordinator.py     DataUpdateCoordinator (5-minute poll)
  config_flow.py     API-key entry, reauthentication, reconfigure
  repairs.py         Repair flow for an account condition that blocks access
  diagnostics.py     Config-entry diagnostics
  entity.py          Base entity (one device per pool unit)
  sensor.py          Sensors driven by statusValues fields
  binary_sensor.py   Connectivity / problem / running states
  image.py           Unit photo by product family (photos in images/)
  frontend/          Pool dashboard (strategy custom:aseko-pool)
  brand/             Icon and logo shown by Home Assistant 2026.3+
  strings.json       Translation source
  translations/      en, cs
  icons.json         Entity icons
docs/images/         Screenshots for the README
hacs.json            HACS metadata
```

## Tests

The tests are black-box: they set the integration up against a mocked Aseko
API and check what Home Assistant shows.

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

`requirements_test.txt` installs the latest Home Assistant, which needs Python
3.14. CI also runs the suite against Home Assistant 2025.3, the oldest release
`hacs.json` allows; keep the two in step when raising the minimum.

## API requests

The integration sends the following headers on every request, as documented in
the integrator API spec:

| Header             | Value                                |
|--------------------|--------------------------------------|
| `Authorization`    | `Bearer <api key>`                   |
| `X-Client-Name`    | `home_assistant`                     |
| `X-Client-Version` | matches `manifest.json` `version`    |
| `Accept-Language`  | Home Assistant's configured language |

## Roadmap

- [ ] Show the unit's firmware version on the device.
- [ ] Instant updates instead of polling every 5 minutes (`cloud_push`).
- [ ] Control the unit from Home Assistant: required values and mode
      (`number`, `select` and `switch` platforms).
