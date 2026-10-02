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
        {'name': 1, 'state': 1, 'fw_states': 1, 'created_on': 1, 'updated_on': 1,
         'nodes': 1},
    ):
        fw_states = doc.get('fw_states', {})
        nodes = sorted(int(n) for n in doc.get('nodes', []))
        rows.append({
            # A workflow is named by its lowest firework id: stable, unique,
            # and what `lpad get_wflows -i` takes.
            'wf_id':      nodes[0] if nodes else None,
            'name':       doc.get('name', '—'),
            'state':      doc.get('state', 'UNKNOWN'),
            'n_fw':       len(fw_states),
            'completed':  sum(1 for s in fw_states.values() if s == 'COMPLETED'),
            'running':    sum(1 for s in fw_states.values() if s == 'RUNNING'),
            'waiting':    sum(1 for s in fw_states.values() if s in ('WAITING', 'READY', 'RESERVED')),
            'fizzled':    sum(1 for s in fw_states.values() if s == 'FIZZLED'),
            'created_on': as_datetime(doc.get('created_on')),
            'updated_on': as_datetime(doc.get('updated_on')),
        })
    from datetime import datetime
    rows.sort(key=lambda r: r['created_on'] or datetime.min, reverse=True)
    return rows


#: States in which a workflow can still change -- the Runs page polls while
#: any workflow is in one of them.
ACTIVE_STATES = frozenset({'RUNNING', 'READY', 'RESERVED', 'WAITING'})


def as_datetime(value):
    """A launchpad timestamp as a naive UTC datetime, or None.

    FireWorks stores workflow times as BSON dates but firework times as ISO
    strings ('2026-10-02T19:17:03.123456'), so the two collections disagree.
    """
    from datetime import datetime
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def list_fireworks(wf_id: int) -> list[dict]:
    """The fireworks of the workflow containing firework *wf_id*.

    Each dict has fw_id, name, state, created_on and updated_on, ordered by
    fw_id -- the order FireWorks created them in.
    """
    import modena
    lp = modena.lpad()
    wf = lp.workflows.find_one({'nodes': int(wf_id)}, {'nodes': 1})
    if wf is None:
        return []
    return [
        {'fw_id': doc['fw_id'], 'name': doc.get('name', '—'),
         'state': doc.get('state', 'UNKNOWN'),
         'created_on': as_datetime(doc.get('created_on')),
         'updated_on': as_datetime(doc.get('updated_on'))}
        for doc in lp.fireworks.find(
            {'fw_id': {'$in': wf['nodes']}},
            {'fw_id': 1, 'name': 1, 'state': 1, 'created_on': 1, 'updated_on': 1},
        ).sort('fw_id', 1)
    ]


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
