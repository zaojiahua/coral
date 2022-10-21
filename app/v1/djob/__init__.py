from app.config.url import delete_unfinished_rds_url
from app.libs.http_client import request
from app.v1.djob.model.djob import DJob
from app.v1.djob.model.djobflow import DJobFlow
from app.v1.djob.model.djobworker import DJobWorker
from app.v1.djob.model.rds import RDS


def djob_init():
    request(method="DELETE", url=delete_unfinished_rds_url)
    djob_flush()


# 清空所有的djob
def djob_flush():
    for djob_worker in DJobWorker.all():
        djob_worker.remove()
    for djob in DJob.all():
        djob.remove()
    for djob_flow in DJobFlow.all():
        djob_flow.remove()
    for rds in RDS.all():
        rds.remove()
    print("jobworker Djob RDS init and delete finished!!")
