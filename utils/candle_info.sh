#!/bin/bash
if [[ -z $1 ]]
   then
       echo "please supply a database name"
       exit 1
fi       
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cat $SCRIPT_DIR/candle_info.sql | sudo -i -u postgres psql -d $1
