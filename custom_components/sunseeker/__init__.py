"""The Sunseeker Lawn Mower integration."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any
import ssl

import paho.mqtt.client as mqtt

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    CONF_MQTT_HOST,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
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
        mqtt_config: dict[str, Any],
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
        self._mqtt_config = mqtt_config
        self._mqtt_client: mqtt.Client | None = None
        self._connected = False

    async def async_setup(self) -> None:
        """Set up MQTT connection."""
        await self.hass.async_add_executor_job(self._setup_mqtt)

    def _setup_mqtt(self) -> None:
        """Set up MQTT client (runs in executor)."""
        self._mqtt_client = mqtt.Client()
        self._mqtt_client.on_connect = self._on_mqtt_connect
        self._mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self._mqtt_client.on_message = self._on_mqtt_message

        # Configure credentials if provided
        if self._mqtt_config.get(CONF_MQTT_USERNAME):
            self._mqtt_client.username_pw_set(
                self._mqtt_config[CONF_MQTT_USERNAME],
                self._mqtt_config.get(CONF_MQTT_PASSWORD, "")
            )

        try:
            self._mqtt_client.connect(
                self._mqtt_config[CONF_MQTT_HOST],
                self._mqtt_config[CONF_MQTT_PORT],
                60
            )
            self._mqtt_client.loop_start()
            _LOGGER.info("MQTT client started for device %s", self.device_id)
        except Exception as err:
            _LOGGER.error("Failed to connect to MQTT broker: %s", err)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            _LOGGER.info("Connected to MQTT broker for device %s", self.device_id)
            client.subscribe(self.response_topic, qos=1)
            self._connected = True
            # Request initial status
            self.hass.async_create_task(self._async_request_initial_status())
        else:
            _LOGGER.error("Failed to connect to MQTT broker, code: %s", rc)
            self._connected = False

    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection."""
        _LOGGER.warning("Disconnected from MQTT broker for device %s", self.device_id)
        self._connected = False

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle MQTT message (runs in executor)."""
        # Schedule handling in HA event loop
        self.hass.async_create_task(self._async_handle_mqtt_message(msg))

    async def _async_handle_mqtt_message(self, msg) -> None:
        """Handle MQTT message in HA event loop."""
        try:
            data = json.loads(msg.payload.decode())
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

    async def _async_request_initial_status(self) -> None:
        """Request initial status after connection."""
        await asyncio.sleep(1)  # Give connection time to stabilize
        await self.async_send_command(CMD_STATUS_UPDATE)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the mower."""
        if not self._connected:
            raise UpdateFailed("MQTT not connected")

        try:
            # Request status update
            await self.async_send_command(CMD_STATUS_UPDATE)
            return self._status_data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with mower: {err}")

    async def async_send_command(self, command: dict[str, Any]) -> None:
        """Send a command to the mower."""
        if not self._mqtt_client or not self._connected:
            raise ConnectionError("MQTT client not connected")

        try:
            payload = json.dumps(command)
            await self.hass.async_add_executor_job(
                self._mqtt_client.publish,
                self.command_topic,
                payload,
                1,  # QoS
                False  # Retain
            )
            _LOGGER.debug("Sent command to %s: %s", self.command_topic, payload)
        except Exception as err:
            _LOGGER.error("Failed to send command: %s", err)
            raise

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

    async def async_shutdown(self) -> None:
        """Shutdown MQTT connection."""
        if self._mqtt_client:
            await self.hass.async_add_executor_job(self._mqtt_client.loop_stop)
            await self.hass.async_add_executor_job(self._mqtt_client.disconnect)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunseeker from a config entry."""
    device_id = entry.data[CONF_DEVICE_ID]
    topic_prefix = entry.data.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)

    # Extract MQTT configuration
    mqtt_config = {
        CONF_MQTT_HOST: entry.data[CONF_MQTT_HOST],
        CONF_MQTT_PORT: entry.data[CONF_MQTT_PORT],
        CONF_MQTT_USERNAME: entry.data.get(CONF_MQTT_USERNAME),
        CONF_MQTT_PASSWORD: entry.data.get(CONF_MQTT_PASSWORD),
    }

    coordinator = SunseekerCoordinator(hass, device_id, mqtt_config, topic_prefix)

    # Set up MQTT connection
    await coordinator.async_setup()

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

        # Shutdown MQTT connection
        await coordinator.async_shutdown()
        
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