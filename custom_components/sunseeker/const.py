"""Constants for the Sunseeker Lawn Mower integration."""

DOMAIN = "sunseeker"

# Configuration keys
CONF_DEVICE_ID = "device_id"
CONF_MQTT_TOPIC_PREFIX = "mqtt_topic_prefix"

# Default values
DEFAULT_NAME = "Sunseeker Lawn Mower"
DEFAULT_TOPIC_PREFIX = "device"

# MQTT Topics (will be formatted with device_id)
TOPIC_COMMAND = "/{prefix}/{device_id}/get"
TOPIC_RESPONSE = "/{prefix}/{device_id}/update"

# Sunseeker Commands
CMD_STOP = {"cmd": 101, "mode": 0}
CMD_START_MOWING = {"cmd": 101, "mode": 1}
CMD_RETURN_DOCK = {"cmd": 101, "mode": 2}
CMD_EDGE_CUTTING = {"cmd": 101, "mode": 4}
CMD_STATUS_UPDATE = {"cmd": 200}
CMD_ROBOT_STATUS = {"cmd": 201}
CMD_ROBOT_NAME = {"cmd": 202}
CMD_CUTTING_SCHEDULE = {"cmd": 203}
CMD_RAIN_DELAY = {"cmd": 205}

# Response command codes
RESP_ROBOT_STATUS = 501
RESP_ROBOT_NAME = 502
RESP_CUTTING_SCHEDULE = 503
RESP_RAIN_STATUS = 505

# State mapping from Sunseeker mode to Home Assistant
MODE_TO_STATE = {
    0: "paused",      # Stopped
    1: "mowing",      # Cutting
    2: "docked",      # Return to dock/docked
    4: "mowing"       # Edge cutting
}

# Sensor types
SENSOR_TYPES = {
    "battery": {
        "name": "Battery",
        "icon": "mdi:battery",
        "device_class": "battery",
        "unit_of_measurement": "%",
        "state_class": "measurement",
    },
    "area_covered": {
        "name": "Area Covered",
        "icon": "mdi:ruler-square",
        "unit_of_measurement": "m²",
        "state_class": "total_increasing",
    },
    "current_area": {
        "name": "Current Area",
        "icon": "mdi:map-marker-radius",
        "unit_of_measurement": "m²",
        "state_class": "measurement",
    },
    "runtime_current": {
        "name": "Current Runtime",
        "icon": "mdi:timer",
        "unit_of_measurement": "min",
        "state_class": "measurement",
    },
    "runtime_total": {
        "name": "Total Runtime",
        "icon": "mdi:timer",
        "unit_of_measurement": "min",
        "state_class": "total_increasing",
    },
    "wifi_signal": {
        "name": "WiFi Signal",
        "icon": "mdi:wifi",
        "unit_of_measurement": "bars",
        "state_class": "measurement",
    },
}

# Device info
DEVICE_MANUFACTURER = "Sunseeker"
DEVICE_MODEL_MAP = {
    "RMA501M20V": "RMA501M20V",
}

# Services
SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_SET_RAIN_DELAY = "set_rain_delay"
SERVICE_EDGE_CUT = "edge_cut"

# Update intervals
STATUS_UPDATE_INTERVAL = 30  # seconds