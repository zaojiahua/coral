from redis_init import redis_client

hash_field = "hash"
fld_field = "fld"
zset_field = "zset"
list_field = "list"
set_field = "set"

_astra_prefix = "astra"
hash_obj_filter = _astra_prefix + "::{cls}::hash::{pk}"
obj_filter_by_field = _astra_prefix + "::{cls}::{field}*"
field_key_without_pk_filter = _astra_prefix + "::{cls}::{field_type}::*::{field_name}"  # * ---> pk  当然 这个 field 拼接不包括 hash
obj_filter_by_field_and_pk = _astra_prefix + "::{cls}::{field}::{pk}*"
astra_key_search_str = _astra_prefix + "::{}::*"
_field_type_name_beside_hash = [fld_field, zset_field, list_field, set_field]
_field_type_name_list = _field_type_name_beside_hash + [hash_field]


def get_full_key_name_list(*name):
    """
    return redis key name by one or muti-key layer
    """
    devide_str = "::"
    middle_str = devide_str.join(name)
    key_str = astra_key_search_str.format(middle_str)
    return redis_client.keys(key_str)
