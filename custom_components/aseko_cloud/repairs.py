"""Repair flows for the Aseko Cloud integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult


class AccessBlockedRepairFlow(RepairsFlow):
    """Confirm-and-refresh flow for the access-blocked issue.

    The single confirm step doubles as a Refresh button: on submit it re-polls
    the affected config entry. If the user has resolved the account condition
    (accepted the Terms of Service, paid the subscription, ...) in the meantime
    the coordinator succeeds, clears the issue and the flow finishes; otherwise
    it aborts and the issue stays.
    """

    def __init__(self, data: dict[str, Any] | None) -> None:
        """Remember the entry to refresh and the localised message to show."""
        data = data or {}
        self._entry_id: str | None = data.get("entry_id")
        self._placeholders = {
            "error": data.get("error", ""),
            "url": data.get("url", ""),
        }

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Start the flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Show the message, then refresh the coordinator on confirmation."""
        if user_input is not None:
            entry = (
                self.hass.config_entries.async_get_entry(self._entry_id)
                if self._entry_id
                else None
            )
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is not None:
                # async_refresh (not async_request_refresh) so we can inspect
                # the outcome synchronously: it awaits the poll to completion.
                await coordinator.async_refresh()
                if not coordinator.last_update_success:
                    return self.async_abort(reason="still_blocked")
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="confirm",
            description_placeholders=self._placeholders,
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create the fix flow for an Aseko Cloud repair issue."""
    return AccessBlockedRepairFlow(data)
