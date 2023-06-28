import os

from app.config.setting import HARDWARE_MAPPING_LIST, CORAL_TYPE
from app.v1.Cuttle.basic.setting import CAMERA_NUM_FILE, set_global_value


def init_camera_num():
    new_hardware_mapping_list = HARDWARE_MAPPING_LIST
    if CORAL_TYPE in [5, 5.3, 5.4] and os.path.exists(CAMERA_NUM_FILE):
        with open(CAMERA_NUM_FILE, "r") as f:
            content = f.read()
            camera_num_list = content.strip(' ').split(' ')
            for camera_id in HARDWARE_MAPPING_LIST:
                if not camera_id.isdigit():
                    continue
                if camera_id not in camera_num_list:
                    new_hardware_mapping_list.remove(camera_id)
            set_global_value('new_hardware_list', new_hardware_mapping_list)
    else:
        set_global_value('new_hardware_list', HARDWARE_MAPPING_LIST)
    return 0

