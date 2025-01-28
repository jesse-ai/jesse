if [ -z "$1" ]; then
  INSTALL_LOC=/usr/local
else
  INSTALL_LOC=${1}
fi
echo "Installing to ${INSTALL_LOC}"
if [ ! -f "${INSTALL_LOC}/lib/libta_lib.a" ]; then
  wget https://github.com/TA-Lib/ta-lib/releases/download/v0.6.1/ta-lib-0.6.1-src.tar.gz -q
  tar -xzf ta-lib-0.6.1-src.tar.gz
  cd ta-lib-0.6.1/ \
  && ./configure --prefix=${INSTALL_LOC}/ \
  && make \
  && which sudo && sudo make install || make install \
  && echo "export LD_LIBRARY_PATH=/usr/local/lib" >> /root/.bashrc
else
  echo "TA-lib already installed, skipping installation"
fi
