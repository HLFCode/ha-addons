#!/usr/bin/with-contenv bashio

# opts is an array which is built into the command line options
declare -a opts

# --device can be either a physical device like /dev/ttyUSB0 or an ip address like 127.0.0.1:1024
# The config has two values, device for physical and tcp_address for tcp communication
if $(bashio::config 'use_serial'); then
    if bashio::config.has_value "device"; then
        opts+=("--device $(bashio::config device)")
    else
        bashio::log.fatal "Use Serial Device is selected but no serial device has been chosen"
        bashio::addon.stop
    fi
else
    if bashio::config.has_value "tcp_address"; then
        opts+=("--device $(bashio::config tcp_address)")
    else
        bashio::log.fatal "Use Serial Device is not selected but no tcp network address has been defined"
        bashio::addon.stop
    fi
fi
#bashio::config <key> <default>
#bashio::services <service> <option>
opts+=("--network_name $(bashio::config network_name heatmiser_network)")
opts+=("--scan_interval $(bashio::config scan_interval 60)")
opts+=("--homeassistant $(bashio::config homeassistant true)")
opts+=("--loglevel $(bashio::config loglevel info)")
opts+=("--mqtt_host $(bashio::config mqtt_host $(bashio::services mqtt host))")
opts+=("--max_address $(bashio::config max_address 10)")
#MQTT
opts+=("--mqtt_port $(bashio::config mqtt_port $(bashio::services mqtt port))")
opts+=("--mqtt_username $(bashio::config mqtt_username $(bashio::services mqtt username))")
opts+=("--mqtt_password $(bashio::config mqtt_password $(bashio::services mqtt password))")
opts+=("--mqtt_prefix $(bashio::config mqtt_prefix heatmiser)")

ADDON_DIR=/heatmiser

bashio::log.info "cmdline options: ${opts[*]}"

cd $ADDON_DIR
# run the heatmiser addon
python3 main.py ${opts[*]}