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
    CONF_MQTT_HOST,
    CONF_MQTT_PORT,
    DEFAULT_TOPIC_PREFIX,
    TOPIC_COMMAND,
    TOPIC_RESPONSE,
    CMD_STATUS_UPDATE,
    CMD_RAIN_DELAY,
    RESP_ROBOT_STATUS,
    RESP_RAIN_STATUS,
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
        self._rain_data = {}
        self._mqtt_config = mqtt_config
        self._mqtt_client: mqtt.Client | None = None
        self._connected = False

    async def async_setup(self) -> None:
        """Set up MQTT connection."""
        _LOGGER.info("Setting up MQTT connection for device %s", self.device_id)
        await self.hass.async_add_executor_job(self._setup_mqtt)

    def _setup_mqtt(self) -> None:
        """Set up MQTT client (runs in executor)."""
        _LOGGER.info("Creating MQTT client for %s:%s",
                     self._mqtt_config[CONF_MQTT_HOST],
                     self._mqtt_config[CONF_MQTT_PORT])

        self._mqtt_client = mqtt.Client()
        self._mqtt_client.on_connect = self._on_mqtt_connect
        self._mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self._mqtt_client.on_message = self._on_mqtt_message

        try:
            _LOGGER.info("Connecting to MQTT broker %s:%s",
                         self._mqtt_config[CONF_MQTT_HOST],
                         self._mqtt_config[CONF_MQTT_PORT])
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
            _LOGGER.info("Subscribing to topic: %s", self.response_topic)
            client.subscribe(self.response_topic, qos=1)
            self._connected = True
            # Request initial status - properly schedule from MQTT thread
            _LOGGER.info("Scheduling initial status request for device %s", self.device_id)
            asyncio.run_coroutine_threadsafe(
                self._async_request_initial_status(),
                self.hass.loop
            )
        else:
            _LOGGER.error("Failed to connect to MQTT broker, code: %s", rc)
            self._connected = False

    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection."""
        _LOGGER.warning("Disconnected from MQTT broker for device %s", self.device_id)
        self._connected = False

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle MQTT message (runs in executor)."""
        # Schedule handling in HA event loop properly
        asyncio.run_coroutine_threadsafe(
            self._async_handle_mqtt_message(msg),
            self.hass.loop
        )

    async def _async_handle_mqtt_message(self, msg) -> None:
        """Handle MQTT message in HA event loop."""
        try:
            payload = msg.payload.decode()
            _LOGGER.debug("Raw MQTT message from %s: %s", msg.topic, payload)

            data = json.loads(payload)
            _LOGGER.info("Received from mower: cmd=%s, data=%s", data.get("cmd"), data)

            # Handle status response
            if data.get("cmd") == RESP_ROBOT_STATUS:
                _LOGGER.info("Processing robot status response for device %s", self.device_id)
                self._status_data = data
                combined_data = {**self._status_data, **self._rain_data}
                _LOGGER.debug("Combined data after status update: %s", combined_data)
                self.async_set_updated_data(combined_data)

                # Update device info if we don't have it yet
                if self._device_info is None:
                    _LOGGER.info("Setting up device info for device %s", self.device_id)
                    self._update_device_info(data)

            # Handle rain status response
            elif data.get("cmd") == RESP_RAIN_STATUS:
                _LOGGER.info("Processing rain status response for device %s", self.device_id)
                self._rain_data = data
                combined_data = {**self._status_data, **self._rain_data}
                _LOGGER.debug("Combined data after rain status update: %s", combined_data)
                self.async_set_updated_data(combined_data)

            else:
                _LOGGER.debug("Ignoring message with cmd=%s", data.get("cmd"))

        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON from mower: %s", msg.payload)
        except Exception as err:
            _LOGGER.error("Error processing MQTT message: %s", err)

    async def _async_request_initial_status(self) -> None:
        """Request initial status after connection."""
        await asyncio.sleep(1)  # Give connection time to stabilize
        await self.async_send_command(CMD_STATUS_UPDATE)
        await asyncio.sleep(0.5)  # Brief delay between commands
        await self.async_send_command(CMD_RAIN_DELAY)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the mower."""
        _LOGGER.debug("Starting data update for device %s", self.device_id)

        if not self._connected:
            _LOGGER.warning("MQTT not connected for device %s", self.device_id)
            raise UpdateFailed("MQTT not connected")

        try:
            # Request status update and rain status
            _LOGGER.debug("Sending status update command to device %s", self.device_id)
            await self.async_send_command(CMD_STATUS_UPDATE)
            await asyncio.sleep(0.5)  # Brief delay between commands
            _LOGGER.debug("Sending rain delay command to device %s", self.device_id)
            await self.async_send_command(CMD_RAIN_DELAY)

            # Combine status and rain data
            combined_data = {**self._status_data, **self._rain_data}
            _LOGGER.debug("Data update complete for device %s, data: %s",
                         self.device_id, combined_data)
            return combined_data
        except Exception as err:
            _LOGGER.error("Error communicating with mower %s: %s", self.device_id, err)
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
        _LOGGER.info("Shutting down MQTT connection for device %s", self.device_id)

        if self._mqtt_client:
            try:
                # Mark as not connected first
                self._connected = False

                # Stop the MQTT loop
                await self.hass.async_add_executor_job(self._mqtt_client.loop_stop)
                _LOGGER.debug("MQTT loop stopped for device %s", self.device_id)

                # Disconnect
                await self.hass.async_add_executor_job(self._mqtt_client.disconnect)
                _LOGGER.debug("MQTT client disconnected for device %s", self.device_id)

                # Clear the client reference
                self._mqtt_client = None

            except Exception as err:
                _LOGGER.error("Error during MQTT shutdown for device %s: %s", self.device_id, err)
        else:
            _LOGGER.debug("No MQTT client to shutdown for device %s", self.device_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunseeker from a config entry."""
    _LOGGER.info("Setting up Sunseeker integration for entry %s", entry.entry_id)

    # Check if entry is already set up
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        _LOGGER.warning("Entry %s already exists, cleaning up first", entry.entry_id)
        await async_unload_entry(hass, entry)

    device_id = entry.data[CONF_DEVICE_ID]
    topic_prefix = DEFAULT_TOPIC_PREFIX  # Always use "device"

    # Extract MQTT configuration
    mqtt_config = {
        CONF_MQTT_HOST: entry.data[CONF_MQTT_HOST],
        CONF_MQTT_PORT: entry.data[CONF_MQTT_PORT],
    }

    coordinator = SunseekerCoordinator(hass, device_id, mqtt_config, topic_prefix)

    # Set up MQTT connection
    try:
        await coordinator.async_setup()
    except Exception as err:
        _LOGGER.error("Failed to set up MQTT connection: %s", err)
        return False

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up platforms
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info("Successfully set up platforms for entry %s", entry.entry_id)
    except Exception as err:
        _LOGGER.error("Failed to set up platforms: %s", err)
        # Clean up coordinator if platform setup fails
        await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return False

    # Register services (only once globally)
    if len(hass.data[DOMAIN]) == 1:  # First integration entry
        try:
            await async_setup_services(hass, coordinator)
            _LOGGER.info("Services registered for Sunseeker integration")
        except Exception as err:
            _LOGGER.error("Failed to set up services: %s", err)

    # Initial data fetch
    try:
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.info("Initial data refresh completed for entry %s", entry.entry_id)
    except Exception as err:
        _LOGGER.warning("Initial data refresh failed: %s", err)
        # Don't fail setup just because initial refresh failed

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Sunseeker integration for entry %s", entry.entry_id)

    # Get coordinator if it exists
    coordinator: SunseekerCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    # Unload platforms first
    unload_ok = True
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            _LOGGER.info("Successfully unloaded platforms for entry %s", entry.entry_id)
        else:
            _LOGGER.warning("Failed to unload some platforms for entry %s", entry.entry_id)
    except Exception as err:
        _LOGGER.error("Error unloading platforms: %s", err)
        unload_ok = False

    # Shutdown coordinator if it exists
    if coordinator:
        try:
            await coordinator.async_shutdown()
            _LOGGER.info("Coordinator shut down for entry %s", entry.entry_id)
        except Exception as err:
            _LOGGER.error("Error shutting down coordinator: %s", err)

    # Remove from hass.data
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Remove services if this was the last entry
        if not hass.data[DOMAIN]:
            try:
                hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)
                hass.services.async_remove(DOMAIN, SERVICE_SET_RAIN_DELAY)
                hass.services.async_remove(DOMAIN, SERVICE_EDGE_CUT)
                _LOGGER.info("Services removed for Sunseeker integration")
            except Exception as err:
                _LOGGER.error("Error removing services: %s", err)

    _LOGGER.info("Unload completed for entry %s, success: %s", entry.entry_id, unload_ok)
    return unload_ok


async def async_setup_services(hass: HomeAssistant, coordinator: SunseekerCoordinator) -> None:
    """Set up services for the integration."""

    # Check if services are already registered
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        _LOGGER.debug("Services already registered, skipping")
        return

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
    try:
        hass.services.async_register(
            DOMAIN, SERVICE_SET_SCHEDULE, set_schedule_service
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_RAIN_DELAY, set_rain_delay_service
        )
        hass.services.async_register(
            DOMAIN, SERVICE_EDGE_CUT, edge_cut_service
        )
        _LOGGER.info("Successfully registered services for Sunseeker integration")
    except Exception as err:
        _LOGGER.error("Failed to register services: %s", err)
        raise