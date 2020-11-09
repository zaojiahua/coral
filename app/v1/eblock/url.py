from flask import Blueprint

from app.v1.eblock.views.eblock import EblockView

eblock = Blueprint("eblock", __name__)

# TEST EXAMPLE FOR EBLOCK
request_body = {
    # block_index = models.IntegerField()
    # block_source = models.CharField()
    # stop_flag = models.BooleanField()
    # ------new-------
    "block_index": 2,
    "device_id": 2,
    "block_source": "Djob",
    "work_path": "./work/",
    "rds_path": "./work/",
    "temp_port_list": ["TA-01", "TA-02"],
    "ip_address": "10.80.3.123",
    "blockName": "createNewTab",
    "unitLists":
        [[{"execCmdDict": {"bkupCmdList": [],
                           "execCmdList": [
                               "<3adbcTool> shell input tap 550 1235",
                               "<4ccmd><sleep>3"],
                           "exptResList": []},
           "execModName": "ADBC",
           "jobUnitName": "ADBC--newBrowserTab"}], [{
            "execCmdDict": {
                "bkupCmdList": [],
                "execCmdList": [
                    "<3adbcTool> shell rm /sdcard/snap.png",
                    "<3adbcTool> shell  screencap -p /sdcard/snap.png",
                    "<3adbcTool> pull /sdcard/snap.png <blkOutPath>snap.png"],
                "exptResList": []},
            "execModName": "ADBC",
            "jobUnitName": "ADBC--2JunitSnapshot"}],
         [{"execCmdDict": {
             "configFile": "E:\\Palm\\joblib\\job-a03de750-6739-4e35-8a31-5a60ca01cf8a\\newTabUrlBoxArea.json",
             "inputImgFile": "<blkInpPath>snap.png",
             "outputFile": "<rdsDatPath>assess",
             "referImgFile": "E:\\Palm\\joblib\\job-a03de750-6739-4e35-8a31-5a60ca01cf8a\\browserNewTab.png",
             "requestName": "assessImgBySURFnHist"},
             "execModName": "IMGTOOL",
             "jobUnitName": "IMGTOOL--isInBrowserNewTab"}],
         [{"execCmdDict": {"bkupCmdList": [],
                           "execCmdList": [
                               "<3adbcTool> shell input keyevent 4",
                               "<3adbcTool> shell input keyevent 4",
                               "<3adbcTool> shell input keyevent 3",
                               "<3adbcTool> shell input keyevent 3"],
                           "exptResList": []},
           "execModName": "ADBC",
           "jobUnitName": "ADBC--BackToHome"}]]}

return_format = [
    {'ADBC': {'result': [0]}},
    {'ADBC': {'result': [0]}},
    {'ADBC': {'result': [0, 1]}, 'TEMPER': {'3_temp': 25.2}},
    {"IMGTOOL": {'timeConsume': 12.87, 'result': [0]}}
]

eblock.add_url_rule("/", view_func=EblockView.as_view("eblcok_create"))
eblock.add_url_rule("/<int:id>/", view_func=EblockView.as_view("eblcok_stop"))
