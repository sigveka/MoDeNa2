"""
@file      MoDeNa workflow runner.
@details   Provides ``modena.run()`` — a high-level wrapper around FireWorks
           ``rapidfire`` that handles launchpad setup, workflow construction,
           and progress reporting.
@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fireworks import Workflow


def run(
    wf_or_models,
    *,
    lpad=None,
    reset: bool = True,
    sleep_time: int = 0,
    timeout: int | None = None,
    name: str = 'modena_workflow',
):
    """Run a MoDeNa workflow using FireWorks rapidfire.

    Accepts either a ready-made FireWorks ``Workflow`` (or ``Firework``) or a
    list of ``SurrogateModel`` instances.  In the latter case the method
    assembles the standard initialisation workflow automatically (equivalent
    to the boilerplate in every ``initModels`` script).

    Args:
        wf_or_models:
            - A ``fireworks.Workflow`` to run as-is.
            - A ``fireworks.Firework`` — wrapped in a single-FW Workflow.
            - A list/iterable of ``SurrogateModel`` instances — the method
              calls ``m.initialisationStrategy().workflow(m)`` for each one
              and chains them from a shared root (the ``initModels`` pattern).
        lpad:
            A ``ModenaLaunchPad`` (or plain ``LaunchPad``) instance.  If
            ``None`` (default), one is created from the active ``MODENA_URI``
            environment variable.
        reset:
            Whether to reset the launchpad before adding the workflow.
            Default ``True``.  Set to ``False`` to append to existing state.
        sleep_time:
            Seconds to sleep between rapidfire polling cycles.  Default 0
            (no sleep between batches).  Use 1–5 for long-running workflows
            to avoid a busy CPU spin.
        timeout:
            Wall-clock timeout in seconds passed to ``rapidfire``.  ``None``
            means no limit.
        name:
            Workflow name used only when ``wf_or_models`` is a model list.
            Ignored for Workflow/Firework inputs.

    Returns:
        The ``ModenaLaunchPad`` used (allows post-run inspection via
        ``.status()`` or ``.state_counts()``).

    Examples::

        import modena
        import flowRate  # registers the model

        # Initialise all registered surrogate models:
        lp = modena.run(list(modena.SurrogateModel.get_instances()))

        # Run a simulation workflow:
        from fireworks import Firework, Workflow
        import twoTankPython
        wf = Workflow([Firework(twoTankPython.m)], name='twoTanksPython')
        modena.run(wf)
    """
    from fireworks import Firework, Workflow
    from fireworks.core.rocket_launcher import rapidfire
    from modena.Launchpad import ModenaLaunchPad, ModenaConnectionError, _fw_strm_lvl
    from modena.SurrogateModel import SurrogateModel, EmptyFireTask

    # ------------------------------------------------------------------ #
    # Resolve launchpad                                                    #
    # ------------------------------------------------------------------ #
    if lpad is None:
        lpad = ModenaLaunchPad.from_modena_uri()  # raises ModenaConnectionError if unreachable

    # ------------------------------------------------------------------ #
    # Build workflow                                                       #
    # ------------------------------------------------------------------ #
    if isinstance(wf_or_models, Workflow):
        wf = wf_or_models
    elif isinstance(wf_or_models, Firework):
        wf = Workflow([wf_or_models])
    else:
        # Assume iterable of SurrogateModel instances — initModels pattern
        models = list(wf_or_models)
        if not models:
            print('[modena] run: no models provided — nothing to do.')
            return lpad
        # Save each model to reset its DB entry to the current in-memory
        # state (empty fitData, initial CFunction bounds, empty parameters).
        # This mirrors what the old SurrogateModel.__init__ did implicitly —
        # it always called save(), wiping any previously accumulated fitData.
        # Now that __init__ only saves on first creation (to prevent subprocess
        # auto-imports from overwriting fitted data), the initModels caller
        # must explicitly reset here.
        for m in models:
            m.save()
        model_ids = ', '.join(m._id for m in models)
        wf = Workflow([Firework([EmptyFireTask()],
                                name=f'init root — {model_ids}')], name=name)
        for m in models:
            wf.append_wf(m.initialisationStrategy().workflow(m), wf.root_fw_ids)

    # ------------------------------------------------------------------ #
    # Reset, add, run                                                      #
    # ------------------------------------------------------------------ #
    if reset:
        lpad.reset('', require_password=False)

    lpad.add_wf(wf)

    ready = lpad.get_fw_ids(query={'state': 'READY'})
    waiting = lpad.get_fw_ids(query={'state': 'WAITING'})
    print(
        f'[modena] run: {len(ready)} READY, {len(waiting)} WAITING — '
        f'starting rapidfire...',
        flush=True,
    )

    rf_kwargs: dict = {'sleep_time': sleep_time, 'strm_lvl': _fw_strm_lvl()}
    if timeout is not None:
        rf_kwargs['timeout'] = timeout

    rapidfire(lpad, **rf_kwargs)

    print(f'[modena] run: done. {lpad.state_summary()}', flush=True)
    return lpad
