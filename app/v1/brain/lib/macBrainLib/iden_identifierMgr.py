"""
此文件作为识别部分的入口 也是接收最终结果的唯一出口
是识别部分的管理者
"""
import os

from app.v1.brain.lib.macBrainTool import macBrain_getProdTOItemList
from . import iden_imgIdentifier, iden_textIdetifier, iden_idenResultSet


def iden_identifier_mgr(brain_handle_req_obj):
    iden_result_set = {}
    # Get BrainHandleRequest Info
    input_img_file = brain_handle_req_obj.getInputImgFile()
    input_text_list = brain_handle_req_obj.getTextList()
    if input_img_file is None and input_text_list is None:
        return iden_result_set

    # get TOItem Info
    apply_TOItem_list = macBrain_getProdTOItemList.get_product_TOItem_list(brain_handle_req_obj.getDevProdName())
    if len(apply_TOItem_list) == 0:
        return iden_result_set
    img_iden_ret_dict = {}
    text_iden_ret_dict = {}

    if input_img_file is not None:
        img_identifier_obj = iden_imgIdentifier.Iden_imgIdentifier(input_img_file, apply_TOItem_list,
                                                                   brain_handle_req_obj)
        img_iden_ret_dict = img_identifier_obj.imgIdentifierMgr()  # TOItem -UUID
    if input_text_list is not None:
        text_iden_obj = iden_textIdetifier.Iden_textIdentifier(input_text_list, apply_TOItem_list)
        text_iden_ret_dict = text_iden_obj.textIdentify()
    if len(img_iden_ret_dict) > 0 or len(text_iden_ret_dict) > 0:
        get_identify_ret_obj = iden_idenResultSet.Iden_idenResultSet(img_iden_ret_dict, text_iden_ret_dict)
        identify_result_set = get_identify_ret_obj.get_identify_ret()
        return identify_result_set

    return iden_result_set
