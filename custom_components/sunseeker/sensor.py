"""Sunseeker lawn mower sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime, UnitOfArea
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunseekerCoordinator
from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sunseeker sensors from a config entry."""
    coordinator: SunseekerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    device_id = config_entry.data[CONF_DEVICE_ID]
    
    entities = []
    for sensor_type, sensor_config in SENSOR_TYPES.items():
        entities.append(
            SunseekerSensor(
                coordinator,
                device_id,
                sensor_type,
                sensor_config,
            )
        )
    
    async_add_entities(entities)


class SunseekerSensor(CoordinatorEntity[SunseekerCoordinator], SensorEntity):
    """Sunseeker sensor entity."""

    def __init__(
        self,
        coordinator: SunseekerCoordinator,
        device_id: str,
        sensor_type: str,
        sensor_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._device_id = device_id
        
        self._attr_name = f"{device_id} {sensor_config['name']}"
        self._attr_unique_id = f"{device_id}_{sensor_type}"
        self._attr_icon = sensor_config.get("icon")
        self._attr_native_unit_of_measurement = sensor_config.get("unit_of_measurement")
        
        # Set device class
        if sensor_config.get("device_class"):
            self._attr_device_class = getattr(SensorDeviceClass, sensor_config["device_class"].upper(), None)
        
        # Set state class
        if sensor_config.get("state_class"):
            if sensor_config["state_class"] == "measurement":
                self._attr_state_class = SensorStateClass.MEASUREMENT
            elif sensor_config["state_class"] == "total_increasing":
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def device_info(self):
        """Return device information."""
        return self.coordinator.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success 
            and self.coordinator.data is not None
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            _LOGGER.debug("No data available for sensor %s", self._attr_unique_id)
            return None

        data = self.coordinator.data
        _LOGGER.debug("Getting value for sensor %s, data available: %s",
                     self._sensor_type, bool(data))

        if self._sensor_type == "battery":
            value = data.get("power")
            _LOGGER.debug("Battery sensor value: %s", value)
            return value
        elif self._sensor_type == "area_covered":
            value = data.get("on_area")
            _LOGGER.debug("Area covered sensor value: %s", value)
            return value
        elif self._sensor_type == "current_area":
            value = data.get("cur_area")
            _LOGGER.debug("Current area sensor value: %s", value)
            return value
        elif self._sensor_type == "runtime_current":
            value = data.get("cur_min")
            _LOGGER.debug("Current runtime sensor value: %s", value)
            return value
        elif self._sensor_type == "runtime_total":
            value = data.get("total_min")
            _LOGGER.debug("Total runtime sensor value: %s", value)
            return value
        elif self._sensor_type == "wifi_signal":
            value = data.get("wifi_lv")
            _LOGGER.debug("WiFi signal sensor value: %s", value)
            return value
        elif self._sensor_type == "rain_status":
            rain_status = data.get("rain_status", 0)
            rain_enabled = data.get("rain_en", False)
            rain_delay_left = data.get("rain_delay_left", 0)

            if not rain_enabled:
                value = "disabled"
            elif rain_status == 1:
                value = "raining"
            elif rain_delay_left > 0:
                value = "delayed"
            else:
                value = "clear"

            _LOGGER.debug("Rain status sensor value: %s (status=%s, enabled=%s, delay_left=%s)",
                         value, rain_status, rain_enabled, rain_delay_left)
            return value

        _LOGGER.warning("Unknown sensor type: %s", self._sensor_type)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return None

        # Add some common attributes for all sensors
        data = self.coordinator.data
        attributes = {
            "station": data.get("station", False),
            "mode": data.get("mode", 0),
        }

        # Add specific attributes for rain status sensor
        if self._sensor_type == "rain_status":
            attributes.update({
                "rain_enabled": data.get("rain_en", False),
                "rain_delay_set_minutes": data.get("rain_delay_set", 0),
                "rain_delay_left_minutes": data.get("rain_delay_left", 0),
                "raw_rain_status": data.get("rain_status", 0),
            })

        return attributes