class FilterUniqueKeyError(Exception):
    """set filter_unique_key is true load to response data format error """
    pass


class RequestMethodError(Exception):
    """request method error"""
    pass


class InstanceExistError(Exception):
    """model error"""
    pass


class InstanceNotExistError(Exception):
    pass
