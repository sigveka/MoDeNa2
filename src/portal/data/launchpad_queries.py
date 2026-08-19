"""
FireWorks launchpad queries — all lpad access lives here.
"""
import modena_portal.config  # noqa: F401 - sets MODENA_URI


def list_workflows() -> list[dict]:
    """
    Return a summary list of all workflows from the FireWorks launchpad.

    Each dict has:
        name        str      workflow name
        state       str      overall state ('COMPLETED', 'RUNNING', ...)
        n_fw        int      total firework count
        completed   int      count of COMPLETED fireworks
        running     int      count of RUNNING fireworks
        waiting     int      count of WAITING fireworks
        fizzled     int      count of FIZZLED fireworks
        created_on  datetime
        updated_on  datetime
    """
    import modena
    lp = modena.lpad()
    rows = []
    for doc in lp.workflows.find(
        {},
        {'name': 1, 'state': 1, 'fw_states': 1, 'created_on': 1, 'updated_on': 1},
    ):
        fw_states = doc.get('fw_states', {})
        rows.append({
            'name':       doc.get('name', '—'),
            'state':      doc.get('state', 'UNKNOWN'),
            'n_fw':       len(fw_states),
            'completed':  sum(1 for s in fw_states.values() if s == 'COMPLETED'),
            'running':    sum(1 for s in fw_states.values() if s == 'RUNNING'),
            'waiting':    sum(1 for s in fw_states.values() if s in ('WAITING', 'READY', 'RESERVED')),
            'fizzled':    sum(1 for s in fw_states.values() if s == 'FIZZLED'),
            'created_on': doc.get('created_on'),
            'updated_on': doc.get('updated_on'),
        })
    from datetime import datetime
    rows.sort(key=lambda r: r['created_on'] or datetime.min, reverse=True)
    return rows


def fizzled_fw_ids() -> list[int]:
    """Firework ids that failed, so the UI can offer to re-queue them."""
    import modena
    return modena.lpad().get_fw_ids(query={'state': 'FIZZLED'})


def queue_summary() -> dict:
    """Counts by state, plus whether anything is waiting for a worker."""
    import modena
    lpad = modena.lpad()
    counts = lpad.state_counts()
    return {
        'counts': counts,
        'ready': counts.get('READY', 0),
        'running': counts.get('RUNNING', 0),
        'fizzled': counts.get('FIZZLED', 0),
    }


def rerun_firework(fw_id: int) -> None:
    """Re-queue one FIZZLED or COMPLETED firework."""
    import modena
    modena.lpad().rerun(int(fw_id))


def defuse_orphans(max_age_seconds: int = 0) -> int:
    """Re-queue fireworks whose worker process died.  Returns the count."""
    import modena
    return modena.lpad().defuse_orphans(max_age_seconds=max_age_seconds)


def retrace(fw_id: int) -> list:
    """Ancestor fireworks of fw_id, roots first.

    ModenaLaunchPad.retrace_to_origin() also prints an ASCII graph; here only
    the returned list is used, rendered as a table.
    """
    import contextlib
    import io

    import modena
    with contextlib.redirect_stdout(io.StringIO()):
        return modena.lpad().retrace_to_origin(int(fw_id))
