# ==================================tboard=======================================

tboard_post_url = "/api/v1/coral/create_tboard/"
insert_tboard_url = "/api/v1/coral/insert_tboard/"
tboard_id_url = "/api/v1/coral/end_tboard/{}/"
tboard_url = "/api/v1/cedar/tboard/{}"

# ==================================rds=======================================

rds_url = "/api/v1/cedar/rds/"
rds_large_amount_url = "/api/v1/coral/search_rds/"
delete_unfinished_rds_url = "/api/v1/cedar/rds/bulk_delete_rds/?rds_id_list=end_time"
rds_create_or_update_url = "/api/v1/coral/rds_create_or_update/"
upload_rds_screen_shot_url = "/api/v1/coral/upload_rds_screen_shot/"
upload_rds_log_file_url = "/api/v1/coral/upload_rds_log_file/"
rds_with_param_url = "/api/v1/cedar/rds/{}"

# ==================================job=======================================

job_url = "/api/v1/cedar/job/"
job_url_filter = "/api/v1/cedar/job/{}"

# ==================================user=======================================

user_url = "/api/v1/cedar/reefuser/"

# ==================================device=======================================

device_url = "/api/v1/cedar/device/"
device_filter_url = "/api/v1/cedar/device/?{}"
device_power_url = "/api/v1/cedar/device_power/"
device_temper_url = "/api/v1/cedar/device_temperature/"
machTempPortUrl = "/api/v1/cedar/temp_port/?port={}"
device_create_update_url = "/api/v1/coral/create_update_device/"
device_assis_create_update_url = "/api/v1/coral/create_or_update_subsidiary_device/"
device_logout = "/api/v1/coral/logout_device/"
coordinate_url = "/api/v1/cedar/control_device_cut_coordinate/"
device_assis_url = "/api/v1/cedar/subsidiary_device/"

# ==================================device_power=======================================

battery_url = "/api/v1/cedar/device_power/"
phone_model_url = "/api/v1/cedar/phone_model/"

cabinet_url = "/api/v1/coral/cabinet_regist/"
power_port_url = "/api/v1/cedar/power_port/"
temp_port_url = "/api/v1/cedar/temp_port/"
device_assis_url = "/api/v1/cedar/subsidiary_device/"

stew_start_url = "/stew/"
adb_exec_url = "/adb/"

box_url = "/api/v1/cedar/woodenbox/"

hw_ocr_token_url = "https://iam.{}.myhuaweicloud.com/v3/auth/tokens"
hw_ocr_url = "https://{}/v1.0/ocr/web-image"

coral_ocr_url = "/ocr"

