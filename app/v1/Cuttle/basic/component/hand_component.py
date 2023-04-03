import os

from app.config.setting import IP_FILE_PATH
from app.v1.Cuttle.basic.setting import set_global_value, CORAL_TYPE, WAIT_POSITION_FILE, get_global_value, MOVE_SPEED, \
    HAND_MAX_X


def read_z_down_from_file():
    Z_DOWN = None
    Z_DOWN_1 = None
    with open(IP_FILE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if "Z_DOWN" in line and line[0] != '#' and "_1" not in line:
                Z_DOWN = float(line.split('=')[1].split('#')[0])
            if "Z_DOWN_1" in line and line[0] != '#' and CORAL_TYPE in [5.3, 5.5]:
                Z_DOWN_1 = float(line.split('=')[1].split('#')[0])
    return Z_DOWN, Z_DOWN_1


def read_wait_position():
    if not os.path.exists(WAIT_POSITION_FILE):
        if CORAL_TYPE in [5.3, 5.5]:
            set_global_value("arm_wait_point", [0, 0, 0])
            set_global_value("arm_wait_point_1", [0, 0, 0])
        elif CORAL_TYPE in [5, 5.1, 5.4]:
            set_global_value("arm_wait_point", [10, -170, 0])
        else:
            set_global_value("arm_wait_point", [10, -95, 0])
    else:
        with open(WAIT_POSITION_FILE, 'rt') as f:
            for line in f.readlines():
                key, value = line.strip('\n').split('=')
                if key == 'arm_wait_point':
                    set_global_value("arm_wait_point", eval(value))
                if key == 'arm_wait_point_1':
                    if CORAL_TYPE == 5.5:
                        set_global_value("arm_wait_point_1", HAND_MAX_X - eval(value))
                    else:
                        set_global_value("arm_wait_point_1", eval(value))

    arm_wait_position = 'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (get_global_value("arm_wait_point")[0],
                                                         get_global_value("arm_wait_point")[1],
                                                         get_global_value("arm_wait_point")[2],
                                                         MOVE_SPEED)
    set_global_value("arm_wait_position", arm_wait_position)
    if CORAL_TYPE == 5.3:
        arm_wait_position_1 = 'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (-get_global_value("arm_wait_point_1")[0],
                                                               get_global_value("arm_wait_point_1")[1],
                                                               get_global_value("arm_wait_point_1")[2],
                                                               MOVE_SPEED)
        set_global_value("arm_wait_position_1", arm_wait_position_1)
    if CORAL_TYPE == 5.5:
        arm_wait_position_1 = 'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (get_global_value("arm_wait_point_1")[0],
                                                               get_global_value("arm_wait_point_1")[1],
                                                               get_global_value("arm_wait_point_1")[2],
                                                               MOVE_SPEED)
        set_global_value("arm_wait_position_1", arm_wait_position_1)

    return 0


def get_wait_position(port):
    return get_global_value("arm_wait_position" + port[-2:]) if port[-1].isdigit() else get_global_value(
        "arm_wait_position")
