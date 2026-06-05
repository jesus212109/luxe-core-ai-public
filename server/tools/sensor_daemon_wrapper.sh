#!/bin/bash
# Wrapper para el sensor daemon — garantiza acceso a /dev/ttyUSB0 vía sg dialout
sg dialout -c "/usr/bin/python3 /home/jesus/TFG/luxe-core-ai/server/sensor_daemon.py --interval 60"
