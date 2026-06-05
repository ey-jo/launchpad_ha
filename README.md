# Launchpad Controller for [Home Assistant](https://www.home-assistant.io/) using MQTT  

## Description
This Project makes it possible to use a Novation Launchpad with Home Assistant using Home Assistant.
It is running in Python using [launchpad.py](https://github.com/FMMT666/launchpad.py/tree/master).

## Prerequisites
- Running Home Assistant Instance
- Running MQTT Broker

## Installation
1. Clone this repository in your home folder:
```bash
git clone https://github.com/ey-jo/launchpad_ha
```

2. Rename [.env.example](.env.example) to [.env](.env) and make adjustments if necessary. You might need to change the path in [launchpad.service](launchpad.service)

3. Execute the [installer](install.sh)

## Starting
Start the service
```bash
sudo systemctl start launchpad.service
```