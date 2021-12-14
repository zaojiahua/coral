import os
import platform
import shutil
import time

from app.execption.outer.error_code.djob import FloderFailToDeleteException


def asure_path_exist(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def deal_dir_file(path):
    if os.path.exists(path):
        if platform.system() == "Windows":
            os.system(f"rd /s /q {path}")
        else:
            os.system(f"rm -rf {path}")


def makedirs_new_folders(path):
    if os.path.exists(path):
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
    else:
        os.makedirs(floder)


def makedirs_new_folder(path, timeout=5):
    start = time.time()
    while os.path.exists(path):
        if time.time() - start > timeout:
            raise FloderFailToDeleteException(description=f"{path} fail to delete")
        deal_dir_file(path)
        time.sleep(.3)

    os.makedirs(path)
    return path


def get_picture_create_time(filepath):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S',
                              time.localtime(os.path.getctime(filepath)))
    return timestamp


def file_rename_from_path(path, prefix, add_timestamp=False):
    for _file_name in os.listdir(path):
        _file_path = os.path.join(path, _file_name)
        if add_timestamp:
            timestamp = get_picture_create_time(os.path.join(path, _file_name)) + ' '
        else:
            timestamp = ''
        os.rename(_file_path, os.path.join(path, f"{timestamp}{prefix}_{_file_name}"))


if __name__ == '__main__':
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    PROJECT_SIBLING_DIR = os.path.dirname(BASE_DIR)

    patha = os.path.join(PROJECT_SIBLING_DIR, "Pacific")

    for floder in os.listdir(patha):
        os.makedirs(os.path.join(patha, floder, "djobwork", "saaaa", "sdsd"))
        file = open(os.path.join(patha, floder, "djobwork", "saaaa", "sdsd", "1.txt"), 'w')
        file.close()
        makedirs_new_folder(os.path.join(patha, floder, "djobwork"))
