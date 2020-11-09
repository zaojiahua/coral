import os

cmd = "git clone -b hand-fixed http://jsp:Orangepond175@10.0.0.57:8251/backend/coral.git && " \
      "cd coral && " \
      "docker-compose up --build"

if "coral" in os.listdir("."):
    cmd = "cd ~/coral && " \
          "docker-compose down && " \
          "cd .. && " \
          "rm -rf coral/ && " + cmd

os.system(cmd)
