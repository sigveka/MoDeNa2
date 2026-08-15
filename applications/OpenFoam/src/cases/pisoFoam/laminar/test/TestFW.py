
from fireworks import FWAction, ScriptTask
from modena import BackwardMappingScriptTask
from os import environ
from os.path import join


class FoamApplication(BackwardMappingScriptTask):
    """
    """
    _fw_name = b'FoamApplication'

    optional_params = ['case_dir']

    def run_task(self, fw_spec):
        """
        """

        try:
            foamrc = join(environ['FOAM_ETC'],'bashrc')
        except KeyError:
            try:
                foamrc = join(fw_spec['_fw_env']['FOAM_ETC'],'bashrc')
            except KeyError:
                return FWAction(defuse_workflow=True)

        print(fw_spec)
        print(fw_spec[self.__class__.__name__])
        super(FoamApplication, self).run_task(fw_spec)



