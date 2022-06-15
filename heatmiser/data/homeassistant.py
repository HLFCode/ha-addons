"""Module of functions to provide json payloads for Home Assistant's auto-discovery"""
import json

HOMEASSISTANT = "homeassistant"
CLIMATEDISCOVERYBASE = f"{HOMEASSISTANT}/climate"
SENSORDISCOVERYBASE = f"{HOMEASSISTANT}/sensor"

def ha_climate_config(name: str, address: int, units: str, maunfacturer: str, model: str, version: str):
    """Returns a json string representing the mqtt payload for Home Assistant's auto-discovery for a Climate entity"""
    topic = f"{CLIMATEDISCOVERYBASE}/{name}"
    payload = {
        'name' : name,
        "mode_cmd_t":f"{topic}/thermostatModeCmd",
        "mode_stat_t":f"{topic}/mode",
        "avty_t":f"{topic}/available",
        "pl_avail":"online",
        "pl_not_avail":"offline",
        "temp_cmd_t":f"{topic}/targetTempCmd",
        "temp_stat_t":f"{topic}/target_temp",
        "curr_temp_t":f"{topic}/current_temp",
        "min_temp":"5",
        "max_temp":"35",
        "temp_step":"1",
        "modes": ["off", "heat"],
        "preset_modes": ["hold 1h", "holiday 1d"],
        "preset_mode_command_topic": f"{topic}/presetCmd",
        "preset_mode_state_topic": f"{topic}/presetState",
        "uniq_id": f"heatmiser_{name}_{address}",
        'unit_of_meas': units,
        'device' : {
            'identifiers': address,
            'manufacturer': maunfacturer,
            'model': model,
            'name': "Heatmiser",
            'suggested_area': "Heating",
            'sw_version': version
        },
        'exp_aft': 600
    }
    return json.dumps(payload)

def ha_sensor_config(name: str, sensor_name: str, address: int, units: str, maunfacturer: str, model: str, version: str):
    """Returns a json string representing the mqtt payload for Home Assistant's auto-discovery for a Sensor entity"""
    sensor_name_snake = sensor_name.replace(' ', '_').lower()
    topic = f"{SENSORDISCOVERYBASE}/{name}_{sensor_name.replace(' ', '_')}"
    payload = {
        'name': f"{name} {sensor_name}",
        "uniq_id": f"heatmiser_{name}_{address}_{sensor_name_snake}",
        'state_topic': f"{CLIMATEDISCOVERYBASE}/{name}/current_temp",
        "avty_t": f"{topic}/available",
        "pl_avail": "online",
        "pl_not_avail": "offline",
        'device': {
            'identifiers': address,
            'manufacturer': maunfacturer,
            'model': model,
            'name': "Heatmiser",
            'suggested_area': "Heating",
            'sw_version': version
        },
        'device_class': 'temperature',
        'unit_of_meas': units,
        'exp_aft': 600
    }
    return json.dumps(payload)
