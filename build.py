import os
import sys

try:
    branch = sys.argv[1]
except Exception:
    branch = "master"

cmd = f"git clone -b {branch} http://jsp:Orangepond175@10.0.0.57:8251/backend/coral.git && " \
      "cd coral && " \
      "docker-compose up --build"

if "coral" in os.listdir("."):
    cmd = "cd ~/coral && " \
          "docker-compose down && " \
          "cd .. && " \
          "rm -rf coral/ && " + cmd

os.system(cmd)
