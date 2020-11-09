def iden_imgIdenResult(TOItem_match_res):
    for TOItem in TOItem_match_res:
        if TOItem_match_res[TOItem] == 0:
            return TOItem
    return {}
