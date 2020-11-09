import os
import sys

# use python3 update.py
container_id = "machexec_container"

try:
    branch = sys.argv[1]
except Exception:
    branch = "master"
cmd = "cd ~ && " \
      "rm -rf coral/ && " \
      f"git clone -b {branch} http://zt:angelreef@10.0.0.57:8251/backend/coral.git && " \
    f"docker cp coral {container_id}:/app && " \
    f"docker restart {container_id}"
os.system(cmd)
