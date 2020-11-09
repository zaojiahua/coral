from flask import request

from app.v1.djob.model.djob import DJob
from app.v1.djob.model.djobworker import DJobWorker
from app.v1.djob.validators.djobSchema import DJobSchema
from app.v1.djob.views import djob_router


def insert_djob_inner(**kwargs):
    validate_data = DJobSchema().load_or_parameter_exception(kwargs)

    djob = DJob(**validate_data)

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
