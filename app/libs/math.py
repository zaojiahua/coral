from functools import reduce

from math import gcd


def list_gcd(_list):
    x = reduce(gcd, _list)
    return x
