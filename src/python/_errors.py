"""
Exceptions that callers must be able to catch without importing the engine.

Import-safe: no side effects, no dependencies.  ``modena.Runner`` pulls in
FireWorks and ``modena.SurrogateModel``, which connects to MongoDB at import,
so the CLI -- which imports lazily for exactly that reason -- could not name
an exception defined there in an ``except`` clause without importing all of
it first.  Re-exported as ``modena.WorkflowFailed`` and
``modena.Runner.WorkflowFailed``.
"""


class WorkflowFailed(RuntimeError):
    """A firework of this run failed; raised by ``modena.run`` / ``launch``.

    ``failures`` is a list of ``(fw_id, name, reason)``.

    Those functions used to return normally whatever happened.  A failing
    simulation is recorded by FireWorks as COMPLETED -- the task ends its
    workflow by returning a defuse action -- so a script doing
    ``modena.run(wf); print("Workflow complete.")`` reported success for a
    run whose simulation had died.
    """

    def __init__(self, failures):
        self.failures = list(failures)
        lines = '\n'.join(f'  fw {i} ({name}): {why}'
                          for i, name, why in self.failures)
        super().__init__(
            f'{len(self.failures)} firework(s) failed:\n{lines}\n'
            'Inspect with:  modena fw status')
