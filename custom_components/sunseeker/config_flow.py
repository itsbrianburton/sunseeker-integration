"""Config flow for Sunseeker Lawn Mower integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_MQTT_TOPIC_PREFIX,
    CONF_MQTT_HOST,
    CONF_MQTT_PORT,
    DEFAULT_NAME,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_MQTT_HOST,
    DEFAULT_MQTT_PORT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Optional(CONF_MQTT_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
        vol.Required(CONF_MQTT_HOST, default=DEFAULT_MQTT_HOST): str,
        vol.Required(CONF_MQTT_PORT, default=DEFAULT_MQTT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.
    
    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # TODO: Add validation logic here if needed
    # For now, we'll just validate that device_id is provided
    device_id = data[CONF_DEVICE_ID].strip()
    if not device_id:
        raise ValueError("Device ID cannot be empty")
    
    # Return info that you want to store in the config entry.
    return {
        "title": data[CONF_NAME],
        "device_id": device_id,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sunseeker Lawn Mower."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ValueError:
                errors["base"] = "invalid_device_id"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Check if device_id is already configured
                await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "mqtt_example": "device/your_device_id_here/update",
            }
        )