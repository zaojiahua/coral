
FROM ubuntu:18.04

ENV PYTHONUNBUFFERED 1

COPY . /app/coral
WORKDIR /app/coral


RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' >/etc/timezone
RUN apt-get update
RUN apt-get install -y wget
RUN apt-get install -y python3.6
RUN apt-get install -y python3-pip
RUN apt-get install -y libsm6
RUN apt-get install -y libxrender1
RUN apt-get install -y --no-install-recommends 	autoconf automake bzip2 dpkg-dev file g++ gcc imagemagick libbz2-dev libc6-dev libcurl4-openssl-dev libdb-dev libevent-dev libffi-dev libgdbm-dev libglib2.0-dev libgmp-dev libjpeg-dev libkrb5-dev liblzma-dev libmagickcore-dev libmagickwand-dev libmaxminddb-dev libncurses5-dev libncursesw5-dev 	libpng-dev libpq-dev libreadline-dev libsqlite3-dev libssl-dev 	libtool libwebp-dev libxml2-dev libxslt-dev libyaml-dev patch unzip xz-utils zlib1g-dev
RUN pip3 install --upgrade pip \
    && pip3 --default-timeout=1000 install  -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

RUN apt-get install -y android-tools-adb && apt-get install -y usbutils && apt-get install -y vim
RUN apt-get install -y kmod
RUN bash setup.sh
RUN cp /opt/MVS/lib/64/. /lib/

#RUN export LD_LIBRARY_PATH=./app/coral/lib:$LD_LIBRARY_PATH

ENTRYPOINT ["gunicorn","-c", "gunicorn.py", "manage:app"]

