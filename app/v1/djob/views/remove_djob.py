from app.execption.outer.error_code.djob import RemoveJobException
from app.v1.djob import DJob
from app.v1.djob.model.djobworker import DJobWorker
from app.v1.djob.views import djob_router


def remove_djob_inner(djob_pk):
    djob = DJob(pk=djob_pk)

    if not djob.exist():
        raise RemoveJobException(description=f"djob({djob_pk}) not exist")

    djob_worker = DJobWorker(pk=djob.device_label)

    if not djob_worker.exist():
        raise RemoveJobException(description=f"djob_worker not exist")

    if djob_worker.using_djob is not None and djob_worker.using_djob == djob:
        djob_worker.using_djob.stop_flag = True
        djob_worker.using_djob.inform_eblock_stop()

        djob_worker.logger.info(f"a working djob has been deleted")
        return {"status": "a working djob has been deleted"}, 204

    else:
        djob_worker.djob_list.lrem(1, djob)

        djob.remove()

        djob_worker.logger.info("a waiting djob has been deleted")
        return {"status": "a waiting djob has been deleted"}, 204


@djob_router.route('/remove_djob/<string:djob_pk>', methods=['DELETE'])
def remove_djob(djob_pk):
    return remove_djob_inner(djob_pk)


if __name__ == '__main__':
    a = {
        "device_label": "cactus---mt6765---34a2dea47d29",
        "job_label": "job-4a5977fa-c309-4984-9456-45b5f6b9ad00",
        "source": "tboard"
    }
    remove_djob_inner(**a)
