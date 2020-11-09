from flask import request, make_response, jsonify

from app.execption.outer.error_code.total import NotFound
from app.v1.djob.model.rds import RDS
from app.v1.djob.views import djob_router


@djob_router.route('/rds/')
def rds_list():
    rds_list = RDS.all(**request.args)
    resp = make_response(jsonify({'all': [rds.json() for rds in rds_list]}), 200)
    resp.headers['length'] = len(rds_list)
    return resp


@djob_router.route('/rds/<int:pk>')
def rds_detail(pk):
    rds_instance = RDS(pk=pk)
    if rds_instance.exist():
        return rds_instance.json(), 200
    raise NotFound
