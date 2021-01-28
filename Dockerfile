
FROM python:3.6

ENV PYTHONUNBUFFERED 1

COPY . /app/coral
WORKDIR /app/coral

RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' >/etc/timezone

RUN pip install --upgrade pip \
    && pip --default-timeout=1000 install  -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

RUN apt-get update && apt-get install -y android-tools-adb && apt-get install -y usbutils && apt-get install -y vim

#RUN export LD_LIBRARY_PATH=./app/coral/lib:$LD_LIBRARY_PATH

ENTRYPOINT ["gunicorn","-c", "gunicorn.py", "manage:app"]

