import logging
from app.config.ip import HOST_IP
from app.config.log import NETWORK_LOG_NAME

logger = logging.getLogger(NETWORK_LOG_NAME)

ROUTER_IP = ".".join(HOST_IP.split('.')[:3]) + '.1'
USERNAME = "AngelReef"
PASSWORD = "2247ac433b8a1e4ac84af68569c44fb4233db3ee4c5d498063562ad52fbe8138a2d3512c16299d8f77cab9a928ee3e1c3a6a40a0a7dfb0fb5d312254d5a063c465912bd86242a57cc14975e60ebc9d5610cad4bbd78bb318f044983c63c076673cb83c59bebabccfbc499e70917569f98b2d68fe87910235cc4eb4070a02161e"

is_route_using = False

stok = None
cookie = None

new_stok = None
NEWPASS = "4s3NyBzdUlUL80v"
