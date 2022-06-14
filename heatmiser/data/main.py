#!/usr/bin/env python
"""
Heatmiser Thermostat serial interface.
The network is scanned for thermostats
Configured thermostats are read routinely
All thermostat data are published to mqtt
Home assistant compatible including discovery of thermostats as climate devices
"""

import logging
from paho.mqtt import client as mqtt_client#, MQTT_ERR_SUCCESS, MQTT_ERR_NO_CONN, MQTT_ERR_QUEUE_SIZE
from datetime import datetime, timedelta
import random
import time
import argparse
import sys

from homeassistant import HOMEASSISTANT, CLIMATEDISCOVERYBASE, SENSORDISCOVERYBASE, ha_climate_config, ha_sensor_config
from heatmiser import HeatmiserThermostat, HEATMISER
from connection import HeatmiserUH1
from utils import GracefulKiller

__author__ = "Mike Ford"
__copyright__ = "Copyright 2022, Mike Ford"
__credits__ = ["Mike Ford", "Neil Trimboy"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Mike Ford"
__email__ = ""
__status__ = "Development"

MQTT_CONNECT_CODES = {
    0:"connected", 
    1:"incorrect protocol version",
    2:"invalid client identifier",
    3:"server unavailable",
    4:"bad username or password",
    5:"not authorised",
    6:"unused"
    }

# mqtt event handlers-------------------------------
def mqtt_on_message(client, userdata, message):
    """
    Event handler for the mqtt client subscription
    Receives messages from topics to which we are subscribed
    """
    try:
        value = message.payload.decode('utf-8')
        _LOGGER.info(f"Received mqtt message: '{message.topic}' = {value}, qos {message.qos}, retain {message.retain}")
        if args.homeassistant and message.topic == f"{HOMEASSISTANT}/status":
            if value == "online":
                # home assistant has just gone online and needs discovery configurations publishing
                for name in thermostats:
                    thermostat = thermostats[name]
                    if thermostat.connected():
                        publish_config(thermostat)
            return

        topic_items = message.topic.split("/")
        sub_topic_count = len(topic_items)
        if sub_topic_count >= 4:
            
            if topic_items[0] == HEATMISER:
                if topic_items[sub_topic_count - 1] == "set":
                    thermo_name = topic_items[sub_topic_count - 3]
                    if thermo_name in thermostats:
                        thermostat = thermostats[thermo_name]
                        property = topic_items[sub_topic_count - 2]
                        if property in thermostat.write_properties:
                            write_prop = thermostat.write_properties[property]
                            thermostat.update_thermostat(write_prop, value)
                        else:
                            _LOGGER.error(f"Received invalid mqtt message {message.topic}: Unable to find property {property}")
                    else:
                        _LOGGER.error(f"Received invalid mqtt message {message.topic}: Unable to find thermostat '{thermo_name}'")
                else:
                    _LOGGER.error(f"Received invalid mqtt message {message.topic}: topic needs to end with ../set")
            
            elif args.homeassistant and f"{topic_items[0]}/{topic_items[1]}" == CLIMATEDISCOVERYBASE:
                thermo_name = topic_items[2]
                if thermo_name in thermostats:
                    thermostat = thermostats[thermo_name]
                    cmd = topic_items[3]
                    if cmd == "thermostatModeCmd":
                        # home assistant 'heat' 'off' corresponds to heatmiser 'heat' 'frost protect'
                        if "run_mode" in thermostat.write_properties:
                            if value in ["heat", "off"]:
                                if thermostat.update_thermostat(thermostat.write_properties["run_mode"], "heating" if value == "heat" else "frost protect"):
                                    _publish_base(client, f"{CLIMATEDISCOVERYBASE}/{thermo_name}/mode", value)
                            else:
                                _LOGGER.error(f"Home assistant mode command needs to be either 'heat' or 'off', received {value}")
                        else:
                            _LOGGER.error(f"Thermostat {thermo_name} does not have a 'run_mode' property")
                    elif cmd == "targetTempCmd":
                        # TODO check limits and validity of value
                        if thermostat.update_thermostat(thermostat.write_properties["room_target_temp"], value):
                            _publish_base(client, f"{CLIMATEDISCOVERYBASE}/{thermo_name}/target_temp", value)
                    elif cmd == "presetCmd":
                        if value == "hold 1h":
                            thermostat.update_thermostat(thermostat.write_properties["holiday_hours"], 0)
                            if thermostat.update_thermostat(thermostat.write_properties["temp_hold_minutes"], 60):
                                _publish_base(client, f"{CLIMATEDISCOVERYBASE}/{thermo_name}/presetState", cmd)
                        elif value == "holiday 1d":
                            thermostat.update_thermostat(thermostat.write_properties["temp_hold_minutes"], 0)
                            if thermostat.update_thermostat(thermostat.write_properties["holiday_hours"], 24):
                                _publish_base(client, f"{CLIMATEDISCOVERYBASE}/{thermo_name}/presetState", cmd)
                        elif value == "none":
                            thermostat.update_thermostat(thermostat.write_properties["temp_hold_minutes"], 0)
                            thermostat.update_thermostat(thermostat.write_properties["holiday_hours"], 0)
                            _publish_base(client, f"{CLIMATEDISCOVERYBASE}/{thermo_name}/presetState", cmd)
                    else:
                        _LOGGER.error(f"Received invalid mqtt message {message.topic}: Not recognised")
                else:
                    _LOGGER.error(f"Received invalid mqtt message {message.topic}: Not recognised")
            else:
                _LOGGER.error(f"Received invalid mqtt message {message.topic}: Not recognised")
        else:
            _LOGGER.error(f"Received invalid mqtt message {message.topic}: Too short")

    except Exception as ex:
        _LOGGER.error(f"Mqtt On_Message unexpected error {ex}")

def mqtt_on_connect(client, userdata, flags, rc):
    """
    Event handler for the mqtt client. Raised when a connection is established
    If successful sets a flag in the client to indicated we are connected
    """
    if rc == 0:
        _LOGGER.info("Connected to MQTT Broker!")
        client.connected_flag = True
    else:
        _LOGGER.error(f"Failed to connect to MQTT broker, {MQTT_CONNECT_CODES[rc]} ({rc})")
# end mqtt event handlers----------------

def _publish_base(client : mqtt_client, topic : str, payload : str):
    """
    Publishes to the mqtt broker on topic with payload
    Returns True or False depending on publishing success
    """
    result = client.publish(topic, payload)
    if result.rc == mqtt_client.MQTT_ERR_SUCCESS:
        try:
            result.wait_for_publish(timeout=0)
            return True
        except ValueError:
            _LOGGER.error(f"Failed to publish topic {topic} with {payload}, queue full")
        except RuntimeError as re:
            _LOGGER.error(f"Failed to publish topic {topic} with {payload}, error: {re}")
        # except Exception as ex:
        #     _LOGGER.error(f"Failed to publish {value} on topic {topic}, unexpected error: {ex}")

    elif result.rc == mqtt_client.MQTT_ERR_NO_CONN:
        _LOGGER.error(f"Failed to publish {topic} with {payload}, not connected to mqtt broker")
    elif result.rc == mqtt_client.MQTT_ERR_QUEUE_SIZE:
        _LOGGER.error(f"Failed to publish {topic} with {payload}, too many queued")
    else:
        _LOGGER.error(f"Failed to publish {topic} with {payload}, unknown return code {result}")
    return False

def publish(client : mqtt_client, prefix :str, name : str, parameter : str, value : str):
    """
    Publishes to the mqtt broker using a specific topic format prefix/name/parameter
    Returns True or False depending on publishing success
    """
    topic = f"{prefix}/{name}/{parameter}"
    return _publish_base(client, topic, value)

def publish_config(thermostat: HeatmiserThermostat):
    """
    Publish the home assistant configuration data to homeassistant/config for discovery
    This is needed for home assistant to configure climate controls for each thermostat
    Needed at startup and every time home assistant publishes homeassistant/status as "online"
    """
    _LOGGER.info("Publishing home assistant discovery config")
    name = thermostat.name
    read_props = thermostat.read_properties
    topic = f"{CLIMATEDISCOVERYBASE}/{name}"
    payload = ha_climate_config(name, thermostat.address, read_props["Units"], read_props['Vendor'], 
        read_props["Type"], read_props["Version"])
    _publish_base(client, topic + "/config", payload)
    
    topic = f"{SENSORDISCOVERYBASE}/{name}_Current_Temp"
    payload = ha_sensor_config(name, "Current Temp", thermostat.address, read_props["Units"], read_props['Vendor'], 
        read_props["Type"], read_props["Version"])
    _publish_base(client, topic + "/config", payload)

# Executable code starts here
if __name__ == '__main__':
    # configure the logger to output preformatted messages
    logging.basicConfig(level=logging.ERROR)
    logger_format = '%(asctime)s %(levelname)-5s %(name)-10s %(lineno)-3s %(message)s'
    hdlr = logging.getLogger().handlers[0]
    fmt = logging.Formatter(logger_format, datefmt='%Y-%m-%d %H:%M:%S')
    hdlr.setFormatter(fmt)

    _LOGGER = logging.getLogger(__name__)

    def check_min(value):
        ivalue = int(value)
        if ivalue < 60:
            raise argparse.ArgumentTypeError(f"{value} needs to be >= 60")
        return ivalue
    def check_byte(value):
        ivalue = int(value)
        if ivalue < 0 or ivalue > 255:
            raise argparse.ArgumentTypeError(f"{value} needs to be between 0 and 255")
        return ivalue

    # define command line arguments
    parser = argparse.ArgumentParser(description='Heatmiser Thermostat with mqtt Communications')
    parser.add_argument('--device', '-d', type=str, help='The physical device controlling the network (e.g. /dev/ttyUSB0)')
    parser.add_argument('--network_name', '-n', type=str, default="heatmiser_network", help='The name of the network (default heatmiser_network)')
    parser.add_argument('--mqtt_host', '-mh', type=str, help='The url or IP address of the mqtt broker')
    parser.add_argument('--mqtt_port', '-mt', type=int, default=1883, help='The port of the mqtt broker (default 1883)')
    parser.add_argument('--mqtt_prefix', '-mx', type=str, default=HEATMISER, help=f"The mqtt topic prefix (default {HEATMISER})")
    parser.add_argument('--mqtt_username', '-mu', required=True, type=str, help='The mqtt broker username')
    parser.add_argument('--mqtt_password', '-mp', required=True, type=str, help='The mqtt broker password')
    parser.add_argument('--scan_interval', '-s', type=check_min, default=60, metavar='[>=60]', help='The interval in seconds between network scans (default 60)')
    parser.add_argument('--max_address', '-m', type=check_byte, default=10, metavar='[0-255]', help='The maximum address to try when looking for thermostats (default 10)')
    parser.add_argument('--homeassistant', '-ha', type=bool, default=True, help='Integrate with Home Assistant discovery (default True')
    parser.add_argument('--loglevel', '-l', type=str, default='info', choices=['debug','info','notice','warning','error'], metavar='[debug|info|notice|warning|error]', help='The log level logging will report (default info)')
    args = parser.parse_args()

    # set the logging level of all modules
    log_level = args.loglevel.upper()
    _LOGGER.setLevel(log_level)
    logging.getLogger(HEATMISER).setLevel(log_level)
    logging.getLogger('connection').setLevel(log_level)
    logging.getLogger('homeassistant').setLevel(log_level)

    _LOGGER.info('Startup')

    # generate client ID randomly
    client_id = f'{args.mqtt_prefix}-mqtt-{random.randint(0, 100)}'

    # Create a communications hub on the serial device
    _LOGGER.info(f"Using '{args.device}', scan interval {args.scan_interval}s")
    HeatmiserUH1 = HeatmiserUH1(args.device, args.network_name)
    _LOGGER.info(f"Scanning '{HeatmiserUH1.name()}' for thermostats from address 0 to {args.max_address}")
    # Create all the thermostats on this network/device
    # TODO this could be performed routinely to pick up network changes (move to main loop?)...
    thermostats = {}
    for address in range(0, args.max_address + 1):
        _LOGGER.info(f"Scanning {HeatmiserUH1.name()} address {address}")
        thermostat_type = HeatmiserThermostat.getThermostatType(HeatmiserUH1, address)
        if thermostat_type != False:
            _LOGGER.info(f"Found {thermostat_type} at address {address}")
            name = f"{HeatmiserUH1.name()}_{address}"
            thermostats[name] = HeatmiserThermostat(address, thermostat_type, HeatmiserUH1,  name)
    if len(thermostats) < 1:
        _LOGGER.error(f"Unable to find any thermostats on hub '{HeatmiserUH1.name()}'")
        sys.exit(1)

    # Create an mqtt client
    client = mqtt_client.Client(client_id)
    client.username_pw_set(args.mqtt_username, args.mqtt_password)
    client.on_connect = mqtt_on_connect
    client.on_message = mqtt_on_message
    # Connect and wait for connection (or failure/timeout)
    timeout_time = datetime.now() + timedelta(seconds=10)
    con_code = client.connect(args.mqtt_host, args.mqtt_port)
    if con_code != 0:
        _LOGGER.error("Failed to connect to mqtt broker, " + MQTT_CONNECT_CODES[con_code])
        sys.exit()
    client.loop_start()
    client.connected_flag = False
    while not client.connected_flag:
        time.sleep(0.1)
        if datetime.now() > timeout_time:
            _LOGGER.error("Failed to connect to mqtt broker, timeout")
            sys.exit()   

    # Subscribe to the writeable properties of every thermostat (in mqtt)
    for name in thermostats:
        thermostat = thermostats[name]
        # Use a single level wildcard (+) to subscribe to all "set" topics for this thermostat
        topic = f'{args.mqtt_prefix}/{name}/+/set'
        _LOGGER.debug(f"Subscribing to {topic}")
        client.subscribe(topic)

        if args.homeassistant:
            # subscribe to the special home assistant climate topics
            client.subscribe(f"{CLIMATEDISCOVERYBASE}/{name}/thermostatModeCmd")
            client.subscribe(f"{CLIMATEDISCOVERYBASE}/{name}/targetTempCmd")
            client.subscribe(f"{CLIMATEDISCOVERYBASE}/{name}/presetCmd")

    published_config = False
    
    # main loop
    try:
        # enable capture of SIGINT and SIGTERM
        killer = GracefulKiller(sigint=True, sigterm=True)
        # loop every second
        last_read_time = datetime.min
        next_scan_time = datetime.now()
        while not killer.kill_now:
            if datetime.now() > next_scan_time:
                next_scan_time = datetime.now() + timedelta(seconds=args.scan_interval)
                for name in thermostats:
                    thermostat = thermostats[name]
                    # read the physical thermostat
                    climate_topic_base = f"{CLIMATEDISCOVERYBASE}/{name}"
                    sensor_topic_base = f"{SENSORDISCOVERYBASE}/{name}_Current_Temp"
                    if thermostat.read_thermostat():
                        read_props = thermostat.read_properties
                        # publish the readable properties on mqtt
                        for key in read_props:
                            publish(client, args.mqtt_prefix, thermostat.name, str(key).lower().replace(" ", "_"), read_props[key])
                        if args.homeassistant:
                            if not published_config:
                                # publish a home assistant dicsovery topic for a climate device
                                publish_config(thermostat)
                                client.subscribe(f"{HOMEASSISTANT}/status")
                                published_config = True
                            # publish the home assistant special topics for climate
                            mode = "heat" if thermostat.read_properties["Run Mode"] == "heating" else "off"
                            current_temp = str(int(float(thermostat.read_properties["Built-in Sensor Temp"])))
                            target_temp = str(int(float(thermostat.read_properties["Room Target Temp"])))
                            _publish_base(client, climate_topic_base + "/available", "online")
                            _publish_base(client, climate_topic_base + "/mode", mode)
                            _publish_base(client, climate_topic_base + "/target_temp", target_temp)
                            _publish_base(client, climate_topic_base + "/current_temp", current_temp)
                            thm = thermostat.read_properties["Temp Hold Minutes"]
                            hh = thermostat.read_properties["Holiday Hours"]
                            if thm == 0 and hh == 0:
                                preset = "none"
                            elif hh > 0:
                                preset = "holiday 1d"
                            elif thm > 0:
                                preset = "hold 1h"
                            _publish_base(client, climate_topic_base + "/presetState", preset)

                            # publish the home assistant special topics for sensor (current temperature)
                            _publish_base(client, sensor_topic_base + "/available", "online")

                    elif args.homeassistant:
                        # unable to read thermostat so indicate it's offline
                        _publish_base(client, climate_topic_base + "/available", "offline")
                        _publish_base(client, sensor_topic_base + "/available", "offline")
                        published_config = False

                _LOGGER.debug("Waiting for next scan...")
            time.sleep(1)

        _LOGGER.info('Shut down request')

    except Exception as ex:
        _LOGGER.error(f'Unexpected exception {ex}')

    for name in thermostats:
        thermostat = thermostats[name]
        if args.homeassistant:
            # publish the home assistant discovery topics to indicate offline
            climate_topic_base = f"{CLIMATEDISCOVERYBASE}/" + name
            _publish_base(client, climate_topic_base + "/available", "offline")
            sensor_topic_base = f"{SENSORDISCOVERYBASE}/{name}_Current_Temp"
            _publish_base(client, sensor_topic_base + "/available", "offline")
    client.disconnect()
    _LOGGER.info("Disconected from mqtt broker")
    client.loop_stop()
    _LOGGER.info("Stopped background mqtt loop")
    
