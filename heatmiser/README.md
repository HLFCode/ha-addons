# Home Assistant Add-on: Heatmiser

This add-on creates a supervisor add-on to communicate with Heatmiser thermostats  
Communication is via RS485 from a com port or via tcp to a serial device on a remote computer  

At startup the RS485 network is scanned and all responding thermostats are registered.  
If Home Assistant integration is enabled (default) they will be auto-discovered by Home Assistant via mqtt

Mqtt broker configuration is automatic but external brokers can be configured

Every scanned address takes a few seconds so limit the maximum address in the configuration

*Not actually tested on any of these architectures*
![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports armhf Architecture][armhf-shield]
![Supports armv7 Architecture][armv7-shield]
![Supports i386 Architecture][i386-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg