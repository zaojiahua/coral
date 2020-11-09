from app.v1.brain.lib import serviceData


def get_product_TOItem_list(prod_name):
    # fern_Path = serviceData.brainLibPath
    TOItem_list = []
    # 遍历BrainLib库下所有的文件夹 [路径存在且不为空]
    if len(serviceData.TOItemInfoObj) == 0:
        return []
    for K, V in serviceData.TOItemInfoObj.items():
        apply_products = V.getProd()
        if apply_products == 0:
            TOItem_list.append(K)
        else:
            if prod_name in apply_products:
                TOItem_list.append(K)
    return TOItem_list
