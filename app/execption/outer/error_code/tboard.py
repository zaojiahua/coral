from app.execption.outer.error_code.total import NotFound


class TboardNotExist(NotFound):
    error_code = 8001
    code = 404
    description = 'tboard not exist'


class TboardStopping(NotFound):
    error_code = 8002
    code = 400
    description = 'tboard in a stop state'


class CreateTboardError(NotFound):
    error_code = 8003
    code = 400
    description = 'create tboard error'


class DutNotExist(NotFound):
    error_code = 8101
    code = 404
    description = 'Dut not exist'
