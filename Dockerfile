# 这是5型柜单独使用的 docker file 运行前需要把海康涉及到的.sh文件全部放到根目录下。
FROM ubuntu:18.04

ENV PYTHONUNBUFFERED 1

RUN apt-get update \
    && apt-get install -y wget \
    && apt-get install -y python3.6 \
    && apt-get install -y python3-pip \
    && apt-get install -y libsm6 \
    && apt-get install -y libxrender1 \
    && apt-get install -y --no-install-recommends autoconf automake bzip2 dpkg-dev file g++ gcc imagemagick libbz2-dev libc6-dev libcurl4-openssl-dev libdb-dev libevent-dev libffi-dev libgdbm-dev libglib2.0-dev libgmp-dev libjpeg-dev libkrb5-dev liblzma-dev libmagickcore-dev libmagickwand-dev libmaxminddb-dev libncurses5-dev libncursesw5-dev 	libpng-dev libpq-dev libreadline-dev libsqlite3-dev libssl-dev 	libtool libwebp-dev libxml2-dev libxslt-dev libyaml-dev patch unzip xz-utils zlib1g-dev

RUN apt-get install -y android-tools-adb && apt-get install -y usbutils && apt-get install -y vim \
    && apt-get install -y kmod \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' >/etc/timezone \
    && apt-get install -y tzdata \
    && apt-get install pngquant

COPY . /app/coral
WORKDIR /app/coral

RUN pip3 install --upgrade pip \
    && pip3 --default-timeout=1000 install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && bash setup.sh \
    && cp -r /opt/MVS/lib/64/. /lib/ \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge -y --auto-remove gcc

ENV LANG C.UTF-8
#RUN export LD_LIBRARY_PATH=./app/coral/lib:$LD_LIBRARY_PATH

ENTRYPOINT ["gunicorn","-c", "gunicorn.py", "manage:app"]

