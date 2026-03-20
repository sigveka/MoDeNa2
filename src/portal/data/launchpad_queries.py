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
