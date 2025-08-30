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
            and self.native_value is not None
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
            
        data = self.coordinator.data
        
        if self._sensor_type == "battery":
            return data.get("power")
        elif self._sensor_type == "area_covered":
            return data.get("on_area")
        elif self._sensor_type == "current_area":
            return data.get("cur_area")
        elif self._sensor_type == "runtime_current":
            return data.get("cur_min")
        elif self._sensor_type == "runtime_total":
            return data.get("total_min")
        elif self._sensor_type == "wifi_signal":
            return data.get("wifi_lv")
        
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return None
            
        # Add some common attributes for all sensors
        data = self.coordinator.data
        return {
            "station": data.get("station", False),
            "mode": data.get("mode", 0),
            "last_updated": self.coordinator.last_update_success_time,
        }