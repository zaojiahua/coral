import collections
import os.path
import re
import time
from collections import deque

import cv2
import numpy as np

from app.execption.outer.error_code.camera import NoSrc, CameraInUse
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.setting import *
from app.execption.outer.error_code.imgtool import CameraNotResponse
from app.config.setting import HARDWARE_MAPPING_LIST
from app.libs import image_utils
from redis_init import redis_client
from app.v1.Cuttle.basic.hand_serial import CameraPower
# 不可去掉，其他文件引用了这里的camera_start
from app.v1.Cuttle.basic.component.camera_component import camera_start

MoveToPress = 9
ImageNumberFile = "__number.txt"


def get_camera_ids():
    camera_ids = []
    for camera_id in HARDWARE_MAPPING_LIST:
        if not camera_id.isdigit():
            continue
        camera_ids.append(camera_id)
    return camera_ids


class CameraHandler(Handler):
    Function = collections.namedtuple("Function", ["condition", "function", "regex"])
    # 这个Function namedtuple是用做adb的结果后处理，根据结果对应匹配后处理函数，最后一个是带入函数的参数
    function_list = [
        Function("shell screencap", "snap_shot", ""),
        Function("shell screenrecord", "get_video", re.compile("--time-limit (.*?) ")),
        Function("shell rm", "ignore", ""),
        Function("pull", "move", re.compile("pull .*? (.*)")),
        Function("exec-out screencap", "screen_shot_and_pull", re.compile("screencap -p > (.*)"))
    ]

    def __init__(self, *args, **kwargs):
        super(CameraHandler, self).__init__(*args, **kwargs)
        # 是否获取高曝光图片
        self.high_exposure = kwargs.get('high_exposure')
        # 是否获取原始图片，非roi图片
        self.original = kwargs.get('original')
        # 摄像机录像
        self.record_video = kwargs.get('record_video')
        self.record_time = kwargs.get('record_time') or 1
        # 性能测试的时候，用来实时的存放图片，如果传入这个参数，则可以实时的获取dp里边的图片
        self.back_up_dq = kwargs.get('back_up_dq')
        self.modify_fps = kwargs.get("modify_fps")
        # 图片拼接时候用到的几个参数
        self.x_min = None
        self.y_min = None
        self.x_max = None
        self.y_max = None
        self.pts = None
        self.weights = None
        # 多摄像机下当前合并到哪个帧号了
        self.cur_frame_num = 0
        self.src = None
        # 多摄像机用来存储图片的缓存
        self.cache_dict = {}

    def before_execute(self, **kwargs):
        # 解析adb指令，区分拍照还是录像
        self.exec_content, opt_type = self.grouping(self.exec_content)
        self.str_func = getattr(self, opt_type)
        return normal_result

    def grouping(self, content):
        for condition, function, regex in self.function_list:
            if condition in content:
                res = re.search(regex, content)
                return res.group(1) if res and res.group() else "", function
        return "", "ignore"

    # 清空管道中的数据
    def clear_queue(self):
        camera_ids = get_camera_ids()
        for camera_id in camera_ids:
            queue = camera_dq_dict.get(self._model.pk + camera_id)
            # 这里会阻塞 直到有元素
            if camera_ret_kwargs_dict[self._model.pk + camera_id].get() == 'end':
                print(f'拍照流程完全结束 {camera_id}', f'管道中还剩余的图片数量：{queue.qsize()}')
            for _ in range(queue.qsize()):
                queue.get()
            print(f'当前管道是否清空 {camera_id}: {queue.qsize()}', queue.empty())

    # 从管道中获取数据
    def get_queue(self, max_count=CameraMax):
        camera_ids = get_camera_ids()
        for camera_id in camera_ids:
            queue = camera_dq_dict.get(self._model.pk + camera_id)
            current_count = 0
            while queue.qsize() > 0 and current_count < max_count:
                self.cache_dict[self._model.pk + camera_id].append(queue.get())
                current_count += 1

    def snap_shot(self):
        # 摄像头数量不一样的时候，方案不同
        camera_ids = get_camera_ids()

        temporary = False if len(camera_ids) > 1 else self.back_up_dq is None
        sync_camera = True if len(camera_ids) > 1 else False
        soft_sync = False
        # 如果录像的话，则按照性能测试来录像
        feature_test = False if self.record_video else self.back_up_dq is None
        for camera_id in camera_ids:
            # 相机正在获取图片的时候 不能再次使用
            if redis_client.get(f"g_bExit_{camera_id}") == "0":
                raise CameraInUse()

            redis_client.set(f"camera_loop_{camera_id}", 0)
            redis_client.set(f'camera_grabbing_{camera_id}', 0)

            # 设置参数，开始拍照
            camera_kwargs_dict[self._model.pk + camera_id].put({
                'high_exposure': self.high_exposure,
                'temporary': temporary,
                'original': self.original,
                'sync_camera': sync_camera,
                'feature_test': feature_test,
                'modify_fps': self.modify_fps,
                'soft_sync': soft_sync
            })
            redis_client.set(f"g_bExit_{camera_id}", '0')

        # 默认使用第一个相机中的截图
        if len(camera_ids) == 1:
            queue = camera_dq_dict.get(self._model.pk + camera_ids[0])
            # 实时的获取到图片
            if self.back_up_dq is not None:
                # 停止时刻由外部进行控制，这里负责图像处理即可
                while get_global_value(CAMERA_IN_LOOP):
                    time.sleep(0.001)
                    # 取图取的很快，基本用不上batch size
                    batch_size = 60
                    while not queue.empty() and batch_size > 0:
                        # print('图片入队')
                        self.back_up_dq.append(queue.get(False))
                        batch_size -= 1
                    # 如果达到了取图的最大限制，并且图片都取出来了，那多等待一些时间
                    if redis_client.get(f"g_bExit_{camera_ids[0]}") == '1' and queue.qsize() == 0:
                        time.sleep(0.5)

                redis_client.set(f"g_bExit_{camera_ids[0]}", "1")
                # 多余的图片删除，及时释放管道里边的内存，如果想多获取一些图片，由外部进行控制
                self.clear_queue()
            else:
                image = queue.get(block=True, timeout=3)['image']
                if not self.original:
                    image = np.rot90(self.get_roi(image, False), 3)

                try:
                    self.src = image
                except UnboundLocalError:
                    raise CameraNotResponse

                # 清空内存
                self.clear_queue()
        else:
            # 判断俩个相机都已经进入到了循环中
            while True:
                all_in_loop = True
                for camera_id in camera_ids:
                    # 注意这里是字符串
                    if redis_client.get(f"camera_loop_{camera_id}") == '0':
                        all_in_loop = False
                        break
                if all_in_loop:
                    break

            need_back_up_dq = True

            # 初始化临时存放图片的缓存
            for camera_id in camera_ids:
                self.cache_dict[self._model.pk + camera_id] = deque(maxlen=CameraMax)

            # 实时的获取到图片
            if self.back_up_dq is not None:
                need_back_up_dq = False
                # 合成到某一个帧号
                self.cur_frame_num = 0
                merge_frame_num = 30

                # 取图的逻辑
                def camera_in_loop():
                    empty_times = 0
                    while get_global_value(CAMERA_IN_LOOP):
                        # 必须等待，否则while死循环导致其他线程没有机会执行
                        time.sleep(merge_frame_num / FpsMax)
                        self.get_queue(merge_frame_num * 1.2)
                        # 判断图片是否全部处理完毕
                        self.cur_frame_num += merge_frame_num
                        if self.merge_frame(camera_ids, self.cur_frame_num) == -1:
                            empty_times += 1
                            if empty_times > 3:
                                break
                        else:
                            empty_times = 0

                # 发送同步信号
                if soft_sync:
                    # 软件同步
                    camera_in_loop()
                else:
                    # 硬件同步
                    with CameraPower(timeout=0):
                        camera_in_loop()

                for camera_id in camera_ids:
                    redis_client.set(f"g_bExit_{camera_id}", "1")

                # 后续再保存一些图片，因为结束点之后还需要一些图片
                self.get_queue(FpsMax)
                self.cur_frame_num += FpsMax
                self.merge_frame(camera_ids, self.cur_frame_num)
            else:
                if self.high_exposure:
                    timeout = 0.4
                else:
                    timeout = 0.1

                # 发送同步信号
                if soft_sync:
                    # 软件同步
                    time.sleep(timeout)
                else:
                    # 硬件同步
                    with CameraPower(timeout=timeout):
                       pass

                for camera_id in camera_ids:
                    redis_client.set(f"g_bExit_{camera_id}", "1")

                # 最后才开始取图 这里有可能管道里边还没把图都放进去，但是只要有一张就行了，所以不用额外处理
                # 如果非要等管道里边所有图片都放进去了，那会影响获取图片的时间
                self.get_queue()

            # 最后再统一处理图片
            if need_back_up_dq:
                self.back_up_dq = []
                self.merge_frame(camera_ids)
                self.back_up_dq.clear()

            # 清空图片内存
            self.clear_queue()
            # 清空为了合并图片特意开的缓存
            for camera_id in camera_ids:
                self.cache_dict[self._model.pk + camera_id].clear()

        # 记录一下拼接以后的图片大小，后边计算的时候需要用到，只在第一次拼接的时候写入，在重置h矩阵的时候，需要将这个值删除
        if self.original and self.src is not None:
            merge_shape = get_global_value('merge_shape')
            if merge_shape is None:
                set_global_value('merge_shape', self.src.shape)
                with open(COORDINATE_CONFIG_FILE, 'at') as f:
                    f.writelines(f'merge_shape={self.src.shape}\n')

        return 0

    def merge_frame(self, camera_ids, merge_frame_num=None):
        # 这里保存的就是同一帧拍摄的所有图片
        self.frames = collections.defaultdict(list)

        # 合并到指定帧号的图片
        try:
            max_frame_num = min([int(self.cache_dict.get(self._model.pk + camera_id)[-1]['frame_num'])
                                 for camera_id in camera_ids])
        except IndexError:
            return -1

        if merge_frame_num is None:
            merge_frame_num = max_frame_num
        else:
            merge_frame_num = merge_frame_num if merge_frame_num < max_frame_num else max_frame_num

        # 同步拍照靠硬件解决，这里获取同步的图片以后，直接拼接即可
        while True:
            stop_flag = True
            for camera_id in camera_ids:
                if len(self.cache_dict.get(self._model.pk + camera_id)) > 0 \
                        and self.cache_dict.get(self._model.pk + camera_id)[0]['frame_num'] <= merge_frame_num:
                    src = self.cache_dict.get(self._model.pk + camera_id).popleft()
                    # 记录来源于哪个相机，方便后续处理
                    src['camera_id'] = camera_id
                    self.frames[src['frame_num']].append(src)
                    stop_flag = False
            if stop_flag:
                break

        # 打印一下，方便debug，等成熟以后删除
        for frame_key in self.frames.keys():
            print(frame_key, len(self.frames[frame_key]), '*' * 10)

        if len(self.frames) == 0:
            return -1

        self.get_syn_frame(camera_ids)

        if len(self.back_up_dq) > 0:
            image = self.back_up_dq[0]['image']
            # 在这里进行运算，选出一张图片，赋给self.src
            self.src = image

            # 写入到文件夹中，测试用
            if self.record_video:
                if os.path.exists('camera'):
                    import shutil
                    shutil.rmtree('camera')
                    os.mkdir('camera')
                else:
                    os.mkdir('camera')

        # 清理内存
        self.frames.clear()

    def get_roi(self, src, multi=True):
        if int(self._model.y1) == 0 and int(self._model.y2) == 0 and int(self._model.x1) == 0 and int(
                self._model.x2) == 0:
            return src
        if multi:
            # 只针对多摄像机，多摄像机没有把参数设置到摄像机上，后续有需求可以直接设置到相机的参数上
            return src[int(self._model.y1):int(self._model.y2), int(self._model.x1):int(self._model.x2)]
        else:
            # 硬件roi获取的是一个较大的区域，需要再次通过软件roi将区域缩到用户设置的roi大小
            return src[int(self._model.y1) - int(self._model.roi_y1): int(self._model.y2) - int(self._model.roi_y1),
                       int(self._model.x1) - int(self._model.roi_x1): int(self._model.x2) - int(self._model.roi_x1)]

    # 从多个相机中获取同步的内容
    def get_syn_frame(self, camera_ids):
        # 判断是否丢帧
        lost_frame_nums = []

        h = get_global_value(MERGE_IMAGE_H)
        for frame_num, frames in self.frames.items():
            if len(frames) != len(camera_ids):
                lost_frame_nums.append(frame_num)
                del frames
                continue

            # 目前只支持拼接俩个相机的数据 1和2中的数据不能乱，因为h矩阵不同
            if int(frames[0]['camera_id']) < int(frames[1]['camera_id']):
                img1 = frames[0]['image']
                img2 = frames[1]['image']
            else:
                img2 = frames[0]['image']
                img1 = frames[1]['image']
            # 有时候俩个相机反了，打开这里
            if CORAL_TYPE == 5.3 and CAMERA_CONVERT:
                img1, img2 = img2, img1

            host_t_1 = frames[0]['host_timestamp']
            host_t_2 = frames[1]['host_timestamp']
            print(frame_num, host_t_2 - host_t_1)

            if h is None:
                # 调试的时候打开
                # cv2.imwrite('camera/camera_1.png', img1)
                # cv2.imwrite('camera/camera_2.png', img2)
                h = self.get_homography(img1, img2)

            result = self.warp_two_images(img2, img1, h)

            if not self.original:
                if CORAL_TYPE == 5.3:
                    result = np.rot90(self.get_roi(result))
                else:
                    result = np.rot90(self.get_roi(result), 3)

            self.back_up_dq.append({'image': result, 'host_timestamp': host_t_1})
            del result

        if lost_frame_nums:
            print('发生了丢帧:', lost_frame_nums, '&' * 10)

    @staticmethod
    def get_homography(img1, img2):
        # 先读取缓存中的矩阵，没有的话再重新生成
        h = get_global_value(MERGE_IMAGE_H)
        if h is None:
            # 判断是否有文件，有的话从文件中读出来，赋值给全局的变量，没有的话现生成一个，然后保存到文件中（方便柜子之间拷贝）。最后还需要提供一个接口，可以删除这个文件，重置全局变量
            if os.path.exists(MERGE_IMAGE_H):
                h = np.load(MERGE_IMAGE_H, allow_pickle=True)
            else:
                h = image_utils.get_homography(img1, img2)
                np.save(MERGE_IMAGE_H, h)
            set_global_value(MERGE_IMAGE_H, h)
        del img1, img2
        return h

    def warp_two_images(self, img1, img2, h):
        h1, w1 = img1.shape[:2]
        if self.pts is None:
            # 有些参数应该只计算一遍，这样加快处理速度
            h2, w2 = img2.shape[:2]
            pts1 = np.float32([[0, 0], [0, h1], [w1, h1], [w1, 0]]).reshape(-1, 1, 2)
            pts2 = np.float32([[0, 0], [0, h2], [w2, h2], [w2, 0]]).reshape(-1, 1, 2)
            pts2_ = cv2.perspectiveTransform(pts2, h)
            pts = np.concatenate((pts1, pts2_), axis=0)
            # print(pts)
            [x_min, y_min] = np.int32(pts.min(axis=0).ravel() - 0.5)
            [x_max, y_max] = np.int32(pts.max(axis=0).ravel() + 0.5)

            # 把数据保存一下，下次直接使用
            self.x_min = x_min
            self.y_min = y_min
            self.x_max = x_max
            self.y_max = y_max
            self.pts = pts

        t = [-self.x_min, -self.y_min]
        ht = np.array([[1, 0, t[0]], [0, 1, t[1]], [0, 0, 1]])

        result = cv2.warpPerspective(img2, ht.dot(h), (self.x_max - self.x_min, self.y_max - self.y_min))
        # cv2.imwrite('D:\\code\\coral-local\\camera\\result_1.png', result)

        result_copy = np.array(result)
        result[t[1]:h1 + t[1], t[0]:w1 + t[0]] = img1
        # print(t)

        sorted_pts = [(int(pos[0][0] + t[0]), int(pos[0][1] + t[1])) for pos in self.pts]
        # 5D的相机组装方式不一样
        if CORAL_TYPE == 5.3:
            sorted_pts = sorted(sorted_pts, key=lambda x: x[1])[2:6]
        else:
            # 取中间的四个点
            sorted_pts = sorted(sorted_pts)[2:6]
        # 调试的时候打开
        # for pos in sorted_pts:
        #     cv2.circle(result, pos, 10, (0, 0, 255), -1)

        sorted_pts = np.array(sorted_pts)
        merge_min_x, merge_min_y = sorted_pts.min(axis=0).ravel()
        merge_max_x, merge_max_y = sorted_pts.max(axis=0).ravel()
        # print(sorted_pts)
        # print(merge_min_x, merge_min_y)
        # print(merge_max_x, merge_max_y)

        if CORAL_TYPE == 5.3:
            # 最耗时的地方，所以提前计算出来权重
            if self.weights is None:
                self.weights = np.ones(result.shape)
                for y in range(merge_min_y, merge_max_y):
                    weight = (y - merge_min_y) / (merge_max_y - merge_min_y)
                    result[y, merge_min_x: merge_max_x, :] = result_copy[y, merge_min_x: merge_max_x, :] * (
                            1 - weight) + result[y, merge_min_x: merge_max_x, :] * weight
                    self.weights[y, merge_min_x: merge_max_x, :] = 1 - weight
            else:
                result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] = \
                    result_copy[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                    self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] + \
                    result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                    (1 - self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :])
        else:
            if self.weights is None:
                self.weights = np.ones(result.shape)
                for r in range(merge_min_x, merge_max_x):
                    weight = (r - merge_min_x) / (merge_max_x - merge_min_x)
                    if t[0] < merge_min_x:
                        result[merge_min_y: merge_max_y, r, :] = \
                            result_copy[merge_min_y: merge_max_y, r, :] * \
                            weight + result[merge_min_y: merge_max_y, r, :] * (1 - weight)
                    else:
                        result[merge_min_y: merge_max_y, r, :] = \
                            result_copy[merge_min_y: merge_max_y, r, :] * \
                            (1 - weight) + result[merge_min_y: merge_max_y, r, :] * weight
                    self.weights[merge_min_y: merge_max_y, r, :] = weight
            else:
                if t[0] < merge_min_x:
                    result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] = \
                        result_copy[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] + \
                        result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        (1 - self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :])
                else:
                    result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] = \
                        result_copy[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        (1 - self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :]) + \
                        result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :]

        return result

    def move(self, *args, **kwargs):
        if hasattr(self, "src") and args[0]:
            cv2.imwrite(args[0], self.src)
            delattr(self, "src")
            return 0
        elif hasattr(self, "video_src") or self.record_video or self.back_up_dq is not None:
            # 暂时注释掉 需要的时候再实现
            pass
            # # 视频分析，存储每一帧图片，并记录总数
            # start = time.time()
            # number = 0
            # total_number = len(self.video_src)
            # with open(get_file_name(args[0]) + ImageNumberFile, "w") as f:
            #     f.write(str(total_number))
            # for i in range(total_number):
            #     cv2.imwrite(get_file_name(args[0]) + f"__{number}.png", self.video_src.popleft())
            #     number += 1
            # delattr(self, "video_src")
            # print("save image time:", time.time() - start)
        else:
            raise NoSrc

    def screen_shot_and_pull(self, *args, **kwargs):
        self.snap_shot()
        self.move(*args)

    # 把他作为一个测试帧率的接口，这样不会受到其他线程的干扰
    def get_video(self, *args, **kwargs):
        # 注意这里可能造成内存泄漏 执行完这个方法最好重启容器
        self.back_up_dq = deque(maxlen=CameraMax)
        self.modify_fps = True
        set_global_value(CAMERA_IN_LOOP, True)
        self.snap_shot()
        # 清空内存
        self.clear_queue()

    def ignore(self, *arg, **kwargs):
        return 0
