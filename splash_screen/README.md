# 视频闪屏检测

## 项目介绍
本项目识别视频内是否存在闪屏。

## 项目代码结构
test_splash_screen.py 本项目测试功能实现代码，会自动遍历文件夹下mp4文件或
指定的某个mp4文件，抽帧后识别视频内是否存在闪屏。

splash_screen.cpython-36m-x86_64-linux-gnu.so
闪屏识别主要模块，主要接口函数 
splash_screen_detect(image_dir, fps, dis_max, splash_num ,max_length)
每10秒判断视频是否存在闪屏问题，第一次发现闪屏时即退出，返回结果和时间
输入参数： 
image_dir 需识别的视频抽帧图文件夹
fps 视频抽帧时每秒抽图的数目，建议视频每秒抽取10帧，抽帧数目会影响阈值设定
dis_max 判断是否闪屏的阈值参数，一般在范围在10-30；建议16，值越小召回越强，准确越低。
splash_num 判断视频是否闪屏的数目阈值，一般范围在3-6；建议4，值越小召回越强，准确越低。
max_length 处理的最长视频时长，单位秒

输出参数：
result 视频整体是否存在闪屏，1存在，0不存在
result_time 发现闪屏片段的开始时间，对应时间点之后10秒内发现闪屏

imageFP.cpython-36m-x86_64-linux-gnu.so 
闪屏识别依赖的其他模块

## lib依赖
本项目的在 CentOS Linux release 7.2 (Final) 系统上编译测试，依赖以下环境
python3.6
ffmpeg 3.4
numpy==1.19.5
opencv-python==4.5.5.62
ImageHash==4.2.1
Pillow==8.4.0


## 快速上手
python3 test_splash_screen.py ../test_data/显示类问题图片/05-闪屏/





