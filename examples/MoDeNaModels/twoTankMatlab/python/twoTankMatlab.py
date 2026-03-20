from modena.Strategy import BackwardMappingScriptTask
import os

m = BackwardMappingScriptTask(
    script=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'bin',
        'twoTanksMacroscopicProblemMatlab'
    )
)
