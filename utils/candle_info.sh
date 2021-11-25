#!/bin/bash
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cat $SCRIPT_DIR/info.sql | sudo -i -u postgres psql -d $1
