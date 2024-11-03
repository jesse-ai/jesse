if [ -z "$1" ]; then
  INSTALL_LOC=/usr/local
else
  INSTALL_LOC=${1}
fi

if [ -z "$2" ]; then
  echo "Error: Build triplet not specified."
  echo "Usage: ./install_the-lib.sh [install_location] [build_triplet]"
  exit 1
else
  BUILD_TRIPLET=${2}
fi

echo "Installing to ${INSTALL_LOC}"
if [ ! -f "${INSTALL_LOC}/lib/libta_lib.a" ]; then
  tar zxvf ta-lib-0.4.0-src.tar.gz
  cd ta-lib \
  && sed -i.bak "s|0.00000001|0.000000000000000001 |g" src/ta_func/ta_utility.h \
  && ./configure --build=${BUILD_TRIPLET} --prefix=${INSTALL_LOC}/ \
  && make \
  && which sudo && sudo make install || make install \
  && echo "export LD_LIBRARY_PATH=/usr/local/lib" >> /root/.bashrc
else
  echo "TA-lib already installed, skipping installation"
fi
