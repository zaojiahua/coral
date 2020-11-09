import sys
import time

highlight_style = "\033[1;33;44m {} \033[0m"


def highlight_print(text):
    print(highlight_style.format(text))


def detail_print(*args, sep=' ', end='\n', file=None):
    # https://www.jb51.net/article/171637.htm
    line = sys._getframe().f_back.f_lineno
    file_name = sys._getframe(1).f_code.co_filename
    args = (str(arg) for arg in args)  # REMIND 防止是数字不能被join
    sys.stdout.write(
        f'"{file_name}:{line}" {time.strftime("%H:%M:%S")} {highlight_style.format("".join(args))}\n')
