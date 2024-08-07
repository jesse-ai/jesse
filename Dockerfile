ARG TEST_BUILD=0
FROM python:3.11-slim AS jesse_basic_env
ENV PYTHONUNBUFFERED 1

# Install necessary packages
RUN apt-get update && apt-get install -y \
    gnupg2 curl \
    && rm -rf /var/lib/apt/lists/*

# Add missing GPG keys
RUN curl -fsSL https://deb.debian.org/debian/archive-key.asc | gpg --dearmor -o /usr/share/keyrings/debian-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list.d/bookworm.list \
    && echo "deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://deb.debian.org/debian bookworm-updates main" >> /etc/apt/sources.list.d/bookworm.list \
    && echo "deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://deb.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list.d/bookworm.list \
    && apt-get update

# Install additional packages
RUN apt-get -y install git build-essential libssl-dev \
    && apt-get clean \
    && pip install --upgrade pip

RUN pip3 install Cython numpy

# Prepare environment
RUN mkdir /jesse-docker
WORKDIR /jesse-docker

# Install TA-lib
COPY docker_build_helpers/* /tmp/
RUN cd /tmp && /tmp/install_ta-lib.sh && rm -r /tmp/*ta-lib*
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Install dependencies
COPY requirements.txt /jesse-docker
RUN pip3 install -r requirements.txt

# Build
COPY . /jesse-docker
RUN pip3 install -e .

FROM jesse_basic_env AS jesse_with_test_0
WORKDIR /home

FROM jesse_basic_env AS jesse_with_test_1
RUN pip3 install codecov pytest-cov
ENTRYPOINT pytest --cov=./ # && codecov

FROM jesse_basic_env AS jesse_final
