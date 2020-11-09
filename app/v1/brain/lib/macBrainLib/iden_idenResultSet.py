class Iden_idenResultSet:
    def __init__(self, img_identify_ret, text_identify_ret):
        self.textIdenRet = text_identify_ret
        self.imgIdentRet = img_identify_ret

    def get_identify_ret(self):
        identify_ret_set = {}
        if len(self.imgIdentRet) > 0:
            identify_ret_set = {"ImgIdentifier": self.imgIdentRet}
        if len(self.textIdenRet) > 0:
            identify_ret_set = {"TextIdentifier": self.textIdenRet}
        return identify_ret_set
