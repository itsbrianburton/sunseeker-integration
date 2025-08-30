"""Sunseeker lawn mower entity."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunseekerCoordinator
from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CMD_STOP,
    CMD_START_MOWING,
    CMD_RETURN_DOCK,
    MODE_TO_STATE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sunseeker lawn mower from a config entry."""
    coordinator: SunseekerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([
        SunseekerLawnMower(
            coordinator,
            config_entry.data[CONF_NAME],
            config_entry.data[CONF_DEVICE_ID],
        )
    ])


class SunseekerLawnMower(CoordinatorEntity[SunseekerCoordinator], LawnMowerEntity):
    """Sunseeker lawn mower entity."""

    _attr_supported_features = (
        LawnMowerEntityFeature.DOCK
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.START_MOWING
    )

    def __init__(
        self,
        coordinator: SunseekerCoordinator,
        name: str,
        device_id: str,
    ) -> None:
        """Initialize the lawn mower."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = f"{device_id}_lawn_mower"
        self._device_id = device_id

    @property
    def device_info(self):
        """Return device information."""
        return self.coordinator.device_info

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Return the current activity."""
        if not self.coordinator.data:
            return None
            
        data = self.coordinator.data
        mode = data.get("mode", 0)
        station = data.get("station", False)
        
        if station:
            return LawnMowerActivity.DOCKED
        
        # Map Sunseeker modes to HA activities
        sunseeker_state = MODE_TO_STATE.get(mode, "paused")
        
        if sunseeker_state == "mowing":
            return LawnMowerActivity.MOWING
        elif sunseeker_state == "docked":
            return LawnMowerActivity.DOCKED
        elif sunseeker_state == "paused":
            return LawnMowerActivity.PAUSED
        else:
            return LawnMowerActivity.ERROR

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return None
            
        data = self.coordinator.data
        return {
            "power": data.get("power", 0),
            "mode": data.get("mode", 0),
            "station": data.get("station", False),
            "on_area": data.get("on_area", 0),
            "on_min": data.get("on_min", 0),
            "total_min": data.get("total_min", 0),
            "cur_min": data.get("cur_min", 0),
            "cur_area": data.get("cur_area", 0),
            "wifi_lv": data.get("wifi_lv", 0),
        }

    async def async_start_mowing(self) -> None:
        """Start mowing."""
        _LOGGER.debug("Starting mowing for %s", self._device_id)
        await self.coordinator.async_send_command(CMD_START_MOWING)
        # Refresh after a short delay to get updated status
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause mowing."""
        _LOGGER.debug("Pausing mowing for %s", self._device_id)
        await self.coordinator.async_send_command(CMD_STOP)
        await self.coordinator.async_request_refresh()

    async def async_dock(self) -> None:
        """Dock the mower."""
        _LOGGER.debug("Docking mower %s", self._device_id)
        await self.coordinator.async_send_command(CMD_RETURN_DOCK)
        await self.coordinator.async_request_refresh()