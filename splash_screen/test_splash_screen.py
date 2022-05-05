# -*- coding: UTF-8 -*-

import os
import sys
import traceback
import time
import splash_screen

fps_num = 15


def get_image_ffmpeg(video_path, image_dirs, fps):
    """
     基于ffmpeg对视频进行抽帧

    :param video_path: MP4视频文件路径
    :param image_dirs: 参考文件夹路径，会自动在下面创建对应视频的文件夹存放抽帧图片
    :param fps: 每秒抽帧数目
    :return: flag，抽帧是否成功
             image_path，保存抽帧图的文件夹路径
    """
    vid = video_path.split('/')[-1].split('.mp4')[0]
    image_path = image_dirs + str(vid) + '/'
    if len(vid) > 1:
        if os.path.exists(image_path):
            os.system('rm -r %s' % image_path)

        os.system('mkdir %s' % image_dirs)
        os.system('mkdir %s' % image_path)
        try:
            result = os.system(
                'ffmpeg -i %s -f image2 -vf fps=fps=%d %s' % (video_path, fps, image_path) + str(vid) + '_%04d.jpg')
            if result == 0:
                flag = True
            else:
                flag = False
        except Exception as e:
            traceback.print_exc()
            flag = False
    else:
        flag = False

    return flag, image_path


def save_result_txt(result):
    """
     保存识别结果到log文件中
    """
    try:
        date = time.strftime("%Y%m%d", time.localtime())
        cur_dir, _ = os.path.split(os.path.abspath(__file__))
        path = os.path.join(cur_dir, "./logs")
        filename = "{}/{}_{}.txt".format(path, "splash_screen_result", date)
        with open(filename, 'a') as f:
            row = "%s\n" % (";".join([str(i) for i in result]))
            f.write(row)
        return
    except Exception as e:
        print(traceback.format_exc())
    return


def splash_video_detect(video_path, max_length=5 * 60):
    """
     基于ffmpeg对视频进行抽帧

    :param video_path: MP4视频文件路径
    :param max_length: 处理的最长视频时长，单位秒
    :return: result，识别结果，1为命中，0为未命中
    """
    cur_dir, _ = os.path.split(video_path)

    image_dirs = os.path.join(cur_dir, 'temp_image/')
    fps = 10

    ret, image_dir = get_image_ffmpeg(video_path, image_dirs, fps)
    if not ret:
        print(" ffmpeg frame drawing flase")
        return 0

    print('fps', fps, ret, image_dir)
    result, result_time = splash_screen.splash_screen_detect(image_dir, fps=fps, dis_max=20, splash_num=4,
                                                             max_length=max_length)
    save_result_txt([video_path, result, result_time])

    return result, result_time


if __name__ == '__main__':

    path1 = sys.argv[1]

    hit_list = []

    time_start = time.time()
    try:
        result = 0
        if '.mp4' in path1:
            result, result_time = splash_video_detect(path1)
            time_record1 = time.time() - time_start
            print('result_time', result_time)

        else:
            file_num = 0
            hit_num = 0
            for root, dirs, files in os.walk(path1):
                for file in files:
                    filepath = os.path.join(root, file)
                    if '.mp4' in filepath:
                        file_num += 1
                        print('******', filepath, '******')
                        result = splash_video_detect(filepath)
                        time_record1 = time.time() - time_start
                        print('time_record1', time_record1)
                        if result == 1:
                            hit_num += 1
                            hit_list.append(file)
                        if file_num:
                            hit_rate = hit_num / float(file_num)
                            print('hit rate', hit_rate, hit_num, file_num)

        print("result is %d" % result)
        print(hit_list)

    except Exception as e:
        traceback.print_exc()
