"""Constants for the Aseko Cloud integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "aseko_cloud"

LOGGER = logging.getLogger(__package__)

# Official Aseko integrator API.
API_BASE_URL = "https://api.aseko.cloud/api/v1"

# Where users generate an API key for the integration.
API_KEYS_URL = "https://account.aseko.cloud/profile/settings/api-keys"

# Sent on every request to identify the client (X-Client-Name / X-Client-Version).
CLIENT_NAME = "home_assistant"
CLIENT_VERSION = "0.1.1"

# The integrator API is poll-only (no push); keep the interval gentle.
SCAN_INTERVAL = timedelta(minutes=5)

MANUFACTURER = "Aseko"
