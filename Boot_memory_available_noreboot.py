# -*- encoding=utf8 -*-

import os
import re
import time
import datetime
import sys
from openpyxl import Workbook

f = os.popen(r"adb devices", "r")
d = f.read()
print(d)


# 输入待测设备SN
device_SN = "7e33bf71"
if len(sys.argv) > 1:
    device_SN = sys.argv[1]
print("测试设备：%s " % device_SN)

now_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
time_str = now_time[0:4]+now_time[5:7]+now_time[8:10]+now_time[11:13]+now_time[14:16]
#
print('now time: '+now_time)
print(time_str)
dname="%s_内存测试_" % device_SN + time_str
os.mkdir(dname)   

wb = Workbook()
# grab the active worksheet
ws = wb.active




def read_meminfo_muti():
    sheet_static_meminfo = wb.create_sheet()
    sheet_static_meminfo.title = "静态内存（5min）"
    sheet_static_meminfo['A1'] = "采样次数"
    sheet_static_meminfo['B1'] = "采样时间"
    sheet_static_meminfo['C1'] = "测试设备： %s" % device_SN
    sheet_static_meminfo['D1'] = "MemFree /MB"
    sheet_static_meminfo['E1'] = "Buffers /MB"
    sheet_static_meminfo['F1'] = "Cached /MB"
    sheet_static_meminfo['G1'] = "可用内存 /MB"
    sheet_static_meminfo['H2'] = "MemFree_avg"
    sheet_static_meminfo['H3'] = "Buffers_avg"
    sheet_static_meminfo['H4'] = "Cached_avg"
    sheet_static_meminfo['H5'] = "MemAvailable_avg"

    # m = os.popen(r"adb -s %s reboot" % device_SN, "r")
    # ret = m.read()
    # print(ret)
    # m.close()

    print("重启中,300s后开始采样内存数据.\n")

    # time.sleep(300)

    print("每隔60s采样一次")

    print("开始采样内存数据：")

    num = 10
    memfree_total = buffer_total = cached_total = 0



    for i in range(num):

        print("\n第 " + str(i + 1) + "/" + str(num) + " 次采样（单位：MB)")
        now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(now_time)
        m = os.popen(r"adb -s %s shell cat /proc/meminfo" % device_SN, "r")
        ret = m.read()
        # print(ret)
        m.close()

        meminfo = ret.split("\n")

        data_proc = {}
        for line in meminfo:
            if "MemTotal" in line:
                MemTotal = re.findall(r"\d+", line)
                data_proc["MemTotal"] = round(int(MemTotal[0])/1024, 2)
            if "MemFree" in line:
                MemFree = re.findall(r"\d+", line)
                data_proc["MemFree"] = round(int(MemFree[0])/1024, 2)
            elif "Buffers" in line:
                Buffers = re.findall(r"\d+", line)
                data_proc["Buffers"] = round(int(Buffers[0])/1024, 2)
            elif "Cached" in line:
                Cached = re.findall(r"\d+", line)
                data_proc["Cached"] = round(int(Cached[0])/1024, 2)
                break
        data_proc["可用内存"] = round((data_proc["MemFree"] + data_proc["Buffers"] + data_proc["Cached"]),2)
        print(data_proc)

        print("可用内存： " + str(data_proc["可用内存"]) + " MB")

        memfree_total = memfree_total + data_proc["MemFree"]
        buffer_total = buffer_total + data_proc["Buffers"]
        cached_total = cached_total + data_proc["Cached"]



        sheet_static_meminfo['A%s' % (i + 2)] = i+1
        sheet_static_meminfo['B%s' % (i + 2)] = now_time
        sheet_static_meminfo['D%s' % (i + 2)] = data_proc["MemFree"]
        sheet_static_meminfo['E%s' % (i + 2)] = data_proc["Buffers"]
        sheet_static_meminfo['F%s' % (i + 2)] = data_proc["Cached"]
        sheet_static_meminfo['G%s' % (i + 2)] = data_proc["可用内存"]

        if (i+1)%3 == 0:
            print("\n正在导出 meminfo 文件……")
            now_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            time_str = now_time[0:4] + now_time[5:7] + now_time[8:10] + now_time[11:13] + now_time[14:16]
            m = os.popen(r"adb -s %s shell dumpsys meminfo >> %s/dumpsys_meminfo_%s_%s.txt" % (device_SN, dname, device_SN, time_str), "r")
            ret = m.read()
            m.close()
            n = os.popen(r"adb -s %s shell cat /proc/meminfo >> %s/proc_meminfo_%s_%s.txt" % (device_SN, dname, device_SN, time_str), "r")
            ret = n.read()
            n.close()
            print("导出 meminfo 文件完毕\n")

        if (i+1) == num:
            sheet_static_meminfo['I2'] = str(round(memfree_total / num, 2))
            sheet_static_meminfo['I3'] = str(round(buffer_total / num, 2))
            sheet_static_meminfo['I4'] = str(round(cached_total / num, 2))
            sheet_static_meminfo['I5'] = str(round((memfree_total+buffer_total+cached_total) / num, 2))

        time.sleep(60)    # 每隔60s采一次样

    print("\n----------------\nMemFree_avg = " + str(round(memfree_total / num, 2)) + " MB")
    print("Buffers_avg = " + str(round(buffer_total / num, 2)) + " MB")
    print("Cached_avg = " + str(round(cached_total / num, 2)) + " MB\n")
    print("\nMemAvailable_avg = " + str(round((memfree_total+buffer_total+cached_total) / num, 2)) + " MB\n\n")

    now_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    time_str = now_time[0:4] + now_time[5:7] + now_time[8:10] + now_time[11:13] + now_time[14:16]
    fname = "%s/%s_内存测试_" % (dname,device_SN) + time_str + ".xlsx"
    wb.save(fname)
    print("内存采集完毕，文件写入完毕")

if __name__ == '__main__':
    read_meminfo_muti()
    print("rest 5 mins then start round2! \n")
    # time.sleep(300)
    read_meminfo_muti()
    print("rest 5 mins then start round3! \n")
    # time.sleep(300)
    read_meminfo_muti()
    print("rest 5 mins then start round4! \n")
    # time.sleep(300)
    read_meminfo_muti()
    print("rest 5 mins then start round5! \n")
    # # time.sleep(300)
    read_meminfo_muti()
    # print("rest 5 mins then start round6! \n")
    # time.sleep(300)
    # read_meminfo_muti()
    # print("rest 5 mins then start round7! \n")
    # time.sleep(300)
    # read_meminfo_muti()



    # for i in range(10):
    #     print("第 " +str(i+1)+ " 次测试")
    #     read_meminfo()
    #     time.sleep(5)

    # time.sleep(5)
    # device_screenoff()   # 灭屏
    # time.sleep(5)
    # print("开始提取灭屏内存")
    # read_meminfo()
    # time.sleep(5)
    # device_screenoff()    # 重新亮屏
    # time.sleep(5)



    # cold_start_meituankdb()
    # time.sleep(10)
    # warm_start_meituankdb()


    # cold_start_zqst()
    # time.sleep(20)
    # warm_start_zqst()


