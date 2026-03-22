"""
Internal logging configuration for the modena package.

Usage by library code
---------------------
    from modena._logging import logger   # root modena logger
    # or per-module:
    import logging
    logger = logging.getLogger('modena.strategy')

Usage by end users / workflow scripts
--------------------------------------
    import modena
    modena.configure_logging(level='WARNING')                    # almost silent
    modena.configure_logging(level='DEBUG', file='run.log')      # modena debug, FW quiet
    modena.configure_logging(level='DEBUG_VERBOSE')              # modena + full FireWorks
    # or via environment variable before running:
    # MODENA_LOG_LEVEL=DEBUG_VERBOSE ./initModels
"""

import logging
import os

# ---------------------------------------------------------------------------
# Custom level: DEBUG_VERBOSE (5) — below DEBUG (10).
# At this level FireWorks output is also enabled at DEBUG.
# ---------------------------------------------------------------------------
DEBUG_VERBOSE = 5
logging.addLevelName(DEBUG_VERBOSE, 'DEBUG_VERBOSE')

# ---------------------------------------------------------------------------
# Package-level logger.  All child loggers ('modena.strategy', etc.) inherit
# this level unless overridden explicitly.
# ---------------------------------------------------------------------------
logger = logging.getLogger('modena')

# Default console handler — plain message text, no timestamp prefix.
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(_console_handler)
logger.setLevel(logging.INFO)

# FireWorks emits INFO for every rocket launch, task start/complete, etc.
# These are routine infrastructure messages; raise to WARNING by default so
# they only appear when something goes wrong.
logging.getLogger('fireworks').setLevel(logging.WARNING)

# mongoengine and pymongo can be chatty at DEBUG; silence them.
logging.getLogger('mongoengine').setLevel(logging.WARNING)
logging.getLogger('pymongo').setLevel(logging.WARNING)


def configure_logging(level: str = 'INFO', file: str = None) -> None:
    """Configure MoDeNa and FireWorks log levels, and optionally log to a file.

    Parameters
    ----------
    level : str
        Log level for modena messages.  Accepted values (case-insensitive):

        ==================  ====================================================
        Level               Effect
        ==================  ====================================================
        ``'WARNING'``       Modena warnings + errors only; FireWorks silent
        ``'INFO'``          Normal modena progress messages (default)
        ``'DEBUG'``         Modena debug output; FireWorks still at WARNING
        ``'DEBUG_VERBOSE'`` Full debug output from modena *and* FireWorks
        ==================  ====================================================

        Can also be set via the ``MODENA_LOG_LEVEL`` environment variable
        (the environment variable takes precedence over the argument).
    file : str or None
        If given, also write all modena + FireWorks messages to this file
        with full timestamps.  The file is opened in append mode.
    """
    effective_level = os.environ.get('MODENA_LOG_LEVEL', level).upper()

    _VALID_LEVELS = {'DEBUG_VERBOSE', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    if effective_level not in _VALID_LEVELS:
        # Warn before changing the level so the message is always visible.
        logger.warning(
            "Unrecognised log level %r — falling back to INFO. "
            "Valid values: %s",
            effective_level, ', '.join(sorted(_VALID_LEVELS)),
        )
        effective_level = 'INFO'

    # Resolve the numeric level; DEBUG_VERBOSE is not in logging's built-in
    # table so we check for it explicitly before falling back to getattr.
    if effective_level == 'DEBUG_VERBOSE':
        numeric = DEBUG_VERBOSE
    else:
        numeric = getattr(logging, effective_level)  # always valid after the guard above

    logger.setLevel(numeric)
    _console_handler.setLevel(numeric)

    # FireWorks: at DEBUG_VERBOSE expose full output; otherwise clamp at WARNING
    # so routine rocket/launchpad INFO messages don't pollute the console.
    if numeric <= DEBUG_VERBOSE:
        fw_numeric = logging.DEBUG
    else:
        fw_numeric = logging.WARNING
    logging.getLogger('fireworks').setLevel(fw_numeric)

    if file:
        fh = logging.FileHandler(file, mode='a')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s  %(levelname)-8s  %(name)s: %(message)s'
        ))
        logger.addHandler(fh)
        logging.getLogger('fireworks').addHandler(fh)
        logging.getLogger('fireworks').setLevel(logging.DEBUG)
