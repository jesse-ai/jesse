FROM ubuntu:20.04

#set timezone, so we avoid tzdata in apt
ENV TZ=Europe/Copenhagen
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# install python with pip, and PostgreSQL
RUN apt-get update && apt-get install -y \
    python3.8 \
    python3-pip \
    postgresql

#copy ta-lib and config for detection arm chips also file
COPY lib/ta-lib-0.4.0-src.tar.gz /tmp/ta-lib-0.4.0-src.tar.gz
COPY lib/config.guess /tmp/config_correct.guess

#install ta-lib. 'make' is runned 2x to account for -j4 fail on first command when multithreaded
RUN cd /tmp && \
  tar -xvzf ta-lib-0.4.0-src.tar.gz && \
  mv config_correct.guess ta-lib/config.guess && \
  cd ta-lib/ && \
  ./configure --prefix=/usr && \
  make -j4  || \ 
  make -j4  && \
  make install

#install jesse and deps.
RUN pip3 install -r https://raw.githubusercontent.com/jesse-ai/jesse/master/requirements.txt && \
    pip3 install -U jesse

#configure postgres
USER postgres
RUN /etc/init.d/postgresql start &&\
    psql --command "CREATE USER jesse_user WITH PASSWORD 'password'" &&\
    psql --command "CREATE DATABASE jesse_db;" && \
    psql --command "GRANT ALL PRIVILEGES ON DATABASE jesse_db to jesse_user;"


USER root
# Expose the PostgreSQL port
EXPOSE 5432

WORKDIR /home

#make 'python' run as 'python3'
RUN echo "alias python='/usr/bin/python3'">>/root/.bashrc

#set default to command to start postgres
ENTRYPOINT  /etc/init.d/postgresql start & /bin/bash