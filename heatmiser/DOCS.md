# Home Assistant Add-on: Heatmiser
Early Heatmiser thermostats (e.g. PTR-N) are linked to a Heatmiser UH1 module via an RS485 2-wire bus.  
This add-on replaces the Heatmiser UH1 module functionality via a serial to RS485 dongle.  
Connection to the RS485 network can be direct (serial port) or over tcp with a remote computer.  
The code includes a supervisor add-on (docker container) in Home Assistant.  

At startup the RS485 bus is scanned and all thermostats which respond are retained.

After the scan is complete the thermostats are reported to Home Assistant as [Climate](https://www.home-assistant.io/integrations/climate/) controls through [mqtt discovery](https://www.home-assistant.io/docs/mqtt/discovery/).  
Additionally the thermostat's current (room) temperature is sent to [mqtt discovery](https://www.home-assistant.io/docs/mqtt/discovery/) as a [sensor](https://www.home-assistant.io/integrations/sensor/)

The climate controls and temperature sensors should be discovered by Home Assistant and stored as entities.  

Control of the thermostat through the climate entity is limited to switching on/off and changing the temperature setpoint

---
## Configuration  

### RS485 (direct serial)
Use this when the serial device is physically connected the the Home Assistant hardware
Set <code>Use Serial Device</code> to True.  
Select the serial-RS485 device from the list provided.  

### TCP  

Use this when the serial device is on a remote computer.  
Set <code>Use Serial Device</code> to False.  
Create a service file on the remote computer (like <code>heatmisertcp.service</code>) in <code>/etc/systemd/system</code> containing  
```[Unit]
Description=Listener for IP to serial link for Heatmiser thermostats
After=network-online.target
ConditionPathExists=/var/log

[Service]
Type=exec
Restart=always
RestartSec=5
PIDFile=/run/nc.pid
# configure the serial port for no echo
ExecStartPre=stty -F /dev/ttyUSB0 4800 cs8 raw  -echo
ExecStart=nc -lk 1024
# force access to tty device
StandardInput=tty-force
# use the same device as stdin
StandardOutput=inherit
# use this device rather than dev/console
TTYPath=/dev/ttyUSB0

[Install]
WantedBy=multi-user.target
```
Note in the above example that the device is /dev/ttyUSB0, the tcp port is 1024 and the baud rate is 4800 BPS.  
Reload systemctl with <code>systemctl daemon-reload</code>  
Enable and start the service with <code>systemctl enable heatmisertcp.service</code> and <code>systemctl start heatmisertcp</code>  

Establish the remote computer's IP address (e.g. by using <code>ifconfig</code>) and set the Heatmiser Add-on <code>TCP Network Address</code> to
<code>\<IP Address\>:\<port\></code> (e.g. <code>192.168.1.35:1024</code>)  

### General

The default configuration will use Home Assistant's [mqtt broker add-on](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md). If you want an alternative broker set up the Host, Username and Password.  

You can give the network a name (e.g. House) by using **Heatmiser Network Name** and limit the network scan to a few addresses to speed up the startup with **Max Scanning Address**. 

To prevent Home Assistant auto-discovery set Integrate with **Home Assistant** to False

### Home Assistant  

Once discovered, Home Assistant will display the climate control as \<network-name\>_\<bus-address\> but you can change this by editing the entitity's name. Similarly the current temperature sensor can be renamed to something more useful (e.g. Kitchen)  

---  

## MQTT  

Thermostats are published to mqtt under the topid defined by <code>MQTT Prefix</code> (default <code>heatmiser</code>).  
Each thermostat publishes a sub-topic <code>\<network-name\>\_\<thermostat address\></code> (default <code>heatmiser_network\_\<n\></code>).  
A typical mqtt hierarchy (with <code>Heatmiser Network Name</code> set to <code>House</code>) would look like:  
```
heatmiser
    House_0
        vendor = Heatmiser
        version = 19
        ...
        built-in_sensor_temp = 22.0
        ...
    House_1
        vendor = Heatmiser
        version = 19
        ...
        built-in_sensor_temp = 21.0
        ...
```
With <code>Integrate with Home Assistant</code> set (the default) the climate and sensor data will also be published as:
```
homeassistant
    climate
        House_0
            available = online
            mode = off
            target_temp = 21
            current_temp = 22
            presetState = none
        House_1
            available = online
            mode = off
            target_temp = 21
            current_temp = 21
            presetState = none
    sensor
        House_0_Current_Temp
            available = online
        House_1_Current_Temp
            available = online
```
---  
## History/Credits
Based on original work by [Neil Trimboy](https://code.google.com/archive/p/heatmiser-monitor-control/)  
Developed by [andylockran](https://github.com/andylockran/heatmiserV3)  
The latter is used by the Home Assistant [Heatmiser](https://www.home-assistant.io/integrations/heatmiser/) integration  
This was developed to:
- enable standalone operation
- mqtt interface
- mqtt Home Assistant auto-discovery (optional)
- automatic recovery from RS485/tcp faults
- automatic discovery of thermostats  
    
The Python code can be run on a computer remote from Home Assistant (e.g. as a standalone daemon) and communicate via mqtt
