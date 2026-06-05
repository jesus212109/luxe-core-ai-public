#!/bin/bash
set -e
SCRIPT=$(readlink -f "$0")
BASE=$(dirname "$(dirname "$(dirname "$SCRIPT")")")
exec sg dialout -c "/usr/bin/python3 $BASE/scripts/fanlamp_control.py \"$1\""
