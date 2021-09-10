import logging

from flask import request

from app.config.log import DJOB_LOG_NAME
from app.v1.djob.model.djob import DJob
from app.v1.djob.model.djobworker import DJobWorker
from app.v1.djob.validators.djobSchema import DJobSchema
from app.v1.djob.views import djob_router
logger = logging.getLogger(DJOB_LOG_NAME)
"""
a = {'device_label': 'chiron---msm8998---8480c8f',
     'job_label': 'job-8fafcfa9-7619-3591-c38d-e394d24864b0',
     'flow_execute_mode': 'SingleSplit',
     'job_flows': [{'id': 509, 'order': 0}],
     'source': 'tboard',
     'tboard_id': '5800',
     'tboard_path': '/Users/darr_en1/tianjinproject/Tboard/5800/'}
"""


def insert_djob_inner(**kwargs):
    # 需要去掉
    # for job_flow in kwargs.get('job_flows', []):
    #     job_flow['name'] = 'test'
    validate_data = DJobSchema().load_or_parameter_exception(kwargs)

    djob = DJob(**validate_data)
    djob.job_flows_order.rpush(*[flow["id"] for flow in sorted(validate_data["job_flows"], key=lambda x: x["order"])])
    djob.job_flows_name.rpush(*[flow["name"] for flow in sorted(validate_data["job_flows"], key=lambda x: x["order"])])
    logger.info(f"create a djobworker and a djob object {djob}")
    djob_worker = DJobWorker(pk=validate_data["device_label"])
    djob_worker.add(djob)

    return {"pk": djob.pk}, 201


@djob_router.route('/insert_djob/', methods=['POST'])
def insert_djob():
    """
    {
        "device_label": "cactus---mt6765---34a2dea47d29",
        "job_label": "job-4a5977fa-c309-4984-9456-45b5f6b9ad00",
        "source": "tboard",
        "tboard_id": 112233,
        "tboard_path": "..."
    }
    """
    return insert_djob_inner(**request.json)


if __name__ == '__main__':
    a = {
        "device_label": "cactus---mt6765---34a2dea47d29",
        "job_label": "job-4a5977fa-c309-4984-9456-45b5f6b9ad00",
        "source": "tboard",
        "tboard_id": 112233,
        "start_time": "2019_10_11_12_22_45",
        "tboard_path": "..."
    }
    # insert_djob_inner(**a)
    import uuid

    print(uuid.uuid3(uuid.NAMESPACE_DNS, 'Djob'))
