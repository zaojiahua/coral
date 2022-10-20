import psutil
import time

from app.config.restart_coral import restart_coral


def resource_monitor():
    # 每隔一秒，监控一下资源的使用情况
    while True:
        # host_timestamp = time.strftime("%Y_%m_%d %H:%M:%S", time.localtime())
        # print('进程数：', len(psutil.pids()))
        # print('cpu使用率：', psutil.cpu_percent(interval=1, percpu=True))
        virtual_memory_percent = psutil.virtual_memory().percent
        # print(f'物理内存使用率：{virtual_memory_percent}%')
        # print(f'交换内存使用率：{psutil.swap_memory().percent}%')
        # net_io_counter = psutil.net_io_counters()
        # print(f'网络发送字节数：{int(net_io_counter[0] / 1024 / 1024)}M')
        # print(f'网络读取字节数：{int(net_io_counter[1] / 1024 / 1024)}M')
        # print('-' * 50)
        if virtual_memory_percent > 95:
            print(f'内存占用达到{virtual_memory_percent}%, 重启容器')
            restart_coral()
        time.sleep(1)
