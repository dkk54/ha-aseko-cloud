"""The version sent to Aseko matches the released integration."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.aseko_cloud.const import CLIENT_VERSION

MANIFEST = Path(__file__).parents[1] / "custom_components/aseko_cloud/manifest.json"


def test_client_version_matches_manifest() -> None:
    """X-Client-Version reports the version in manifest.json."""
    assert CLIENT_VERSION == json.loads(MANIFEST.read_text())["version"]
