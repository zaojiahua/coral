import copy
import os, sys, pathlib
from distutils.core import setup
from Cython.Build import cythonize


def execute_code(dir_paths):

    files = [i + '/*.py' for i in dir_paths]
    # add settings.py
    # files.append('reef/settings.py')

    if 'build_ext' in sys.argv:
        setup(ext_modules=cythonize(files, language_level=3))
    else:
        for item in dir_paths:
            for dirpath, foldernames, filenames in os.walk(item):
                for file in filenames:
                    if dirpath == item + '/config':
                        break
                    if file.endswith('.py') or file.endswith('.c') or file.endswith('.pyc'):
                        os.remove(dirpath + '/' + file)


def get_dir_name(p):
    dir_list = []
    for child in p.iterdir():
        if '__pycache__' in str(child):
            continue
        if child.is_dir():
            dir_list.append(str(child))
            child_dir_list = get_dir_name(child)
            dir_list.extend(child_dir_list)
        else:
            continue
    return dir_list


if __name__ == '__main__':
    p = pathlib.Path('app')
    dir_path_list = get_dir_name(p)
    dir_path_list.append('app')

    copy_dir_path_list = copy.deepcopy(dir_path_list)
    # 没有py文件的目录剔除，否者编译会出错
    for dir_path in dir_path_list:
        py_file_list = list(pathlib.Path(dir_path).glob('*.py'))
        if not py_file_list:
            print(f'Not have py file dir: {dir_path}')
            copy_dir_path_list.remove(dir_path)

    print(f'dir list: {copy_dir_path_list}')
    execute_code(copy_dir_path_list)