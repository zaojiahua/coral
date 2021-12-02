import logging
import os
import subprocess
import sys
import time
import threading

from app.config.log import DOOR_LOG_NAME
from app.libs.log import setup_logger


class AdbCommand(object):
    def __init__(self):
        if sys.platform.startswith("win"):
            self.adbCmdPrefix = "adb "
        else:
            self.adbCmdPrefix = "~/bin/adb "
        self.subproc = None
        self.logger = setup_logger(DOOR_LOG_NAME, f'{DOOR_LOG_NAME}.log')

    def make_one_cmd(self, *commands):
        command_string = self.adbCmdPrefix
        for c in commands:
            command_string += (" " + c)
        return command_string

    def run_cmd(self, one_adb_cmd_string, expect_result="", retry=1, timeout=3):
        for r in range(0, retry):
            if 0 == self.run_cmd_internal(one_adb_cmd_string, expect_result, timeout):
                return 0
        return 1

    def run_cmd_to_get_result(self, one_cmd_string, timeout=3):
        self.logger.debug("runCmdToGetResult : " + one_cmd_string + ", timeout: " + str(timeout))
        run_thread = ShellCmdThread(one_cmd_string)
        run_thread.start()
        result = ""
        for r in range(timeout * 4):
            time.sleep(0.2)
            if run_thread.is_finished():
                result = run_thread.get_result()
                # run_thread = ShellCmdThread(one_cmd_string)
                # run_thread.start()
                self.logger.debug("adbCmd run get result: " + str(result))
                break
        if not run_thread.is_finished():
            run_thread.terminate_thread()
        return result

    def run_cmd_internal(self, one_cmd_string, expect_result, timeout):
        self.logger.debug("adbCmd run: " + one_cmd_string + ", expect: " + expect_result + ", timeout: " + str(timeout))
        run_thread = ShellCmdThread(one_cmd_string)
        run_thread.start()
        result = ""
        for r in range(timeout * 2):
            time.sleep(0.5)
            if run_thread.is_finished():
                result = run_thread.get_result()
                self.logger.debug("adbCmd run get result: " + str(result))
                break
        if not run_thread.is_finished():
            run_thread.terminate_thread()
            return -1
        if (len(expect_result) > 0) and (expect_result in result):
            return 0
        return 1

    def fix_command(self):
        self.logger.warning("receive problem of device offline, try to kill adb server")
        self.subproc = subprocess.Popen("adb kill-server", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.subproc.wait()
        self.subproc = subprocess.Popen("adb start-server", shell=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
        self.subproc.wait()
        self.subproc = subprocess.Popen("adb root", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.subproc.wait()
        self.subproc = subprocess.Popen("adb remount", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.subproc.wait()


class ShellCmdThread(threading.Thread):
    def __init__(self, one_cmd_string):
        threading.Thread.__init__(self)
        self.isExeDone = False
        self.oneCmdString = one_cmd_string
        self.exeResult = ""
        self.subproc = None
        self.logger = setup_logger(DOOR_LOG_NAME, f'{DOOR_LOG_NAME}.log')

    def run(self):
        self.isExeDone = False
        self.logger.debug("exeThread running " + self.oneCmdString + os.linesep)
        self.subproc = subprocess.Popen(self.oneCmdString, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        restr = self.subproc.communicate()[0]
        self.exeResult = restr.strip().decode()
        self.logger.debug("ShellCmdThread run end return " + self.exeResult + os.linesep)
        self.isExeDone = True

    def is_finished(self):
        return self.isExeDone

    def get_result(self):
        return self.exeResult

    def terminate_thread(self):
        if (not self.isExeDone) and (self.subproc is not None):
            try:
                self.subproc.terminate()
            except Exception as e:
                self.logger.error("Got exception in ShellCmdThread-terminateThread: " + str(e))
        return 0


def get_room_version(s_id):
    adb_cmd_obj = AdbCommand()
    color_os = adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.version.opporom")
    rom_version = adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.display.ota")
    if len(rom_version) == 0:
        rom_version = adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.display.id")
    rom_version = color_os + "_" + rom_version if rom_version is not "" and color_os is not "" else \
        adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.version.incremental")
    return rom_version
