#!/bin/bash

if [ -z "$1" ]; then
  INSTALL_LOC=/usr/local
else
  INSTALL_LOC=${1}
fi
echo "Installing to ${INSTALL_LOC}"

if [ ! -f "${INSTALL_LOC}/lib/libta_lib.a" ]; then
  # Download and extract ta-lib source
  tar zxvf ta-lib-0.4.0-src.tar.gz
  cd ta-lib

  # Update config.guess and config.sub
  echo "Downloading updated config.guess and config.sub from savannah.gnu.org"
  wget -O config.guess 'http://savannah.gnu.org/cgi-bin/viewcvs/*checkout*/config/config/config.guess'
  wget -O config.sub 'http://savannah.gnu.org/cgi-bin/viewcvs/*checkout*/config/config/config.sub'

  # Apply patch and configure
  sed -i.bak "s|0.00000001|0.000000000000000001 |g" src/ta_func/ta_utility.h
  ./configure --prefix=${INSTALL_LOC}/

  # Build and install
  make
  if which sudo; then
    sudo make install
  else
    make install
  fi

  # Update library path
  echo "export LD_LIBRARY_PATH=/usr/local/lib" >> /root/.bashrc

  # Verify installation
  if [ -f "${INSTALL_LOC}/include/ta-lib/ta_defs.h" ]; then
    echo "TA-Lib headers installed successfully."
  else
    echo "Error: TA-Lib headers not found."
    exit 1
  fi

  if [ -f "${INSTALL_LOC}/lib/libta_lib.a" ]; then
    echo "TA-Lib library installed successfully."
  else
    echo "Error: TA-Lib library not found."
    exit 1
  fi
else
  echo "TA-lib already installed, skipping installation"
fi
