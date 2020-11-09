"""
此文件作为决策部分唯一入口，唯一出口 相当于决策部分的管理者
"""


def dec_decision_maker_mgr(identify_ret_set):
    # TODO Weight allocation of images and text
    if identify_ret_set == {}:
        return {}
    return identify_ret_set["ImgIdentifier"]
