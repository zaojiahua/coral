def get_value(inkey, jsdata):
    ret = None
    try:
        if inkey in jsdata.keys():
            ret = jsdata[inkey]
    except Exception as e:
        print("error in getValue: " + str(e))
    return ret
