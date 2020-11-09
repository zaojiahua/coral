import json
import os

from app.v1.Cuttle.imgToolSvc.lib.assistFunc.imgToolHelpFunc import get_area_image
from app.v1.Cuttle.imgToolSvc.lib.imgCompareLib import compareBySurf, compareByCVHist


def read_refer_info(refer_info):
    area_dict = {}
    config_info = None
    if "configPath" in refer_info.keys():
        if os.path.exists(refer_info["configPath"]):
            with open(refer_info["configPath"], 'r') as fh:
                config_info = json.load(fh)
    if config_info is not None:
        for k, v in config_info.items():
            if "area" in k:
                area_dict[k] = v
    if len(area_dict) is 0:
        return {}
    else:
        return area_dict


def surf_a_hist(refer_img, input_img):
    good_match = compareBySurf.compare_by_surf(refer_img, input_img)
    d = compareByCVHist.compare_by_np_array(refer_img, input_img)

    return good_match, d


def get_area(img, area):
    im = get_area_image(img, area)
    return im


def judge(good_match, d):
    if d > 0.90 and good_match > 50:
        return 0
    else:
        return 1
