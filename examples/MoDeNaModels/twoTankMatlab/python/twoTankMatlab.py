import os
from modena.Strategy import BackwardMappingScriptTask


class TwoTankMatlabModel(BackwardMappingScriptTask):
    """Macroscopic two-tank MATLAB simulation task."""

    _fw_name = '{{twoTankMatlab.TwoTankMatlabModel}}'
    optional_params = None

    def __init__(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            super().__init__(*args, **kwargs)
            return
        script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'bin', 'twoTanksMacroscopicProblemMatlab'
        )
        super().__init__(script=script, **kwargs)


m = TwoTankMatlabModel()
