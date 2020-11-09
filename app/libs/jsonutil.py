import json


def dump_json_file(json_data, output_file):
    data = json.dumps(json_data, sort_keys=True, indent=4, ensure_ascii=True)
    try:
        with open(output_file, "w") as f:
            f.write(data)
    except Exception as e:
        print("error occurs while writing file" + str(e))
        return -1
    return 0


def read_json_file(input_file):
    ret_js_data = {}
    try:
        with open(input_file, "rb") as f:
            ret_js_data = json.load(f)
    except Exception as e:
        print("error occurs while reading file" + str(e))
    return ret_js_data


def get_value(inkey, jsdata):
    ret = None
    try:
        if inkey in jsdata.keys():
            ret = jsdata[inkey]
    except Exception as e:
        print("error in getValue: " + str(e))
    return ret
