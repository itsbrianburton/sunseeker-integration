"""The Sunseeker Lawn Mower integration."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_TOPIC_PREFIX,
    TOPIC_COMMAND,
    TOPIC_RESPONSE,
    CMD_STATUS_UPDATE,
    RESP_ROBOT_STATUS,
    STATUS_UPDATE_INTERVAL,
    DEVICE_MANUFACTURER,
    SERVICE_SET_SCHEDULE,
    SERVICE_SET_RAIN_DELAY,
    SERVICE_EDGE_CUT,
)

PLATFORMS: list[Platform] = [Platform.LAWN_MOWER, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


class SunseekerCoordinator(DataUpdateCoordinator):
    """Sunseeker lawn mower data coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        topic_prefix: str = DEFAULT_TOPIC_PREFIX,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=STATUS_UPDATE_INTERVAL),
        )
        self.device_id = device_id
        self.topic_prefix = topic_prefix
        self.command_topic = TOPIC_COMMAND.format(
            prefix=topic_prefix, device_id=device_id
        )
        self.response_topic = TOPIC_RESPONSE.format(
            prefix=topic_prefix, device_id=device_id
        )
        self._device_info: DeviceInfo | None = None
        self._status_data = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the mower."""
        try:
            # Request status update
            await self.async_send_command(CMD_STATUS_UPDATE)
            return self._status_data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with mower: {err}")

    async def async_send_command(self, command: dict[str, Any]) -> None:
        """Send a command to the mower."""
        try:
            payload = json.dumps(command)
            await mqtt.async_publish(
                self.hass, self.command_topic, payload, qos=1, retain=False
            )
            _LOGGER.debug("Sent command to %s: %s", self.command_topic, payload)
        except Exception as err:
            _LOGGER.error("Failed to send command: %s", err)
            raise

    @callback
    def handle_mqtt_message(self, msg) -> None:
        """Handle MQTT message from mower."""
        try:
            data = json.loads(msg.payload)
            _LOGGER.debug("Received from mower: %s", data)
            
            # Handle status response
            if data.get("cmd") == RESP_ROBOT_STATUS:
                self._status_data = data
                self.async_set_updated_data(data)
                
                # Update device info if we don't have it yet
                if self._device_info is None:
                    self._update_device_info(data)
                    
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON from mower: %s", msg.payload)
        except Exception as err:
            _LOGGER.error("Error processing MQTT message: %s", err)

    def _update_device_info(self, data: dict[str, Any]) -> None:
        """Update device information."""
        model = data.get("model", "Unknown")
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=f"Sunseeker Lawn Mower ({self.device_id})",
            manufacturer=DEVICE_MANUFACTURER,
            model=model,
            sw_version=str(data.get("version", "Unknown")),
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        return self._device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunseeker from a config entry."""
    device_id = entry.data[CONF_DEVICE_ID]
    topic_prefix = entry.data.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    
    coordinator = SunseekerCoordinator(hass, device_id, topic_prefix)
    
    # Subscribe to MQTT topic
    await mqtt.async_subscribe(
        hass, coordinator.response_topic, coordinator.handle_mqtt_message, qos=1
    )
    
    # Store coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await async_setup_services(hass, coordinator)
    
    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: SunseekerCoordinator = hass.data[DOMAIN][entry.entry_id]
        
        # Unsubscribe from MQTT
        await mqtt.async_unsubscribe(hass, coordinator.response_topic)
        
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove services if this was the last entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)
            hass.services.async_remove(DOMAIN, SERVICE_SET_RAIN_DELAY)
            hass.services.async_remove(DOMAIN, SERVICE_EDGE_CUT)
    
    return unload_ok


async def async_setup_services(hass: HomeAssistant, coordinator: SunseekerCoordinator) -> None:
    """Set up services for the integration."""
    
    async def set_schedule_service(call: ServiceCall) -> None:
        """Set cutting schedule service."""
        schedule_data = {
            "cmd": 103,
            "auto": call.data.get("auto", False),
            "pause": call.data.get("pause", False),
        }
        
        # Add schedule for each day
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for day in days:
            if day.lower() in call.data:
                day_schedule = call.data[day.lower()]
                schedule_data[day] = {
                    "slice": [
                        {
                            "start": int(slot["start"]),
                            "end": int(slot["end"])
                        }
                        for slot in day_schedule.get("slots", [])
                    ],
                    "trimming": day_schedule.get("trimming", True)
                }
            else:
                schedule_data[day] = {}
        
        await coordinator.async_send_command(schedule_data)
    
    async def set_rain_delay_service(call: ServiceCall) -> None:
        """Set rain delay service."""
        command = {
            "cmd": 105,
            "rain_en": call.data.get("enabled", True),
            "rain_delay_set": call.data.get("delay_minutes", 180),
        }
        await coordinator.async_send_command(command)
    
    async def edge_cut_service(call: ServiceCall) -> None:
        """Start edge cutting service."""
        command = {"cmd": 101, "mode": 4}
        await coordinator.async_send_command(command)
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, set_schedule_service
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_RAIN_DELAY, set_rain_delay_service
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EDGE_CUT, edge_cut_service
    )