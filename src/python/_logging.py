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

import json
import logging
import os
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Custom level: DEBUG_VERBOSE (5) — below DEBUG (10).
# At this level FireWorks output is also enabled at DEBUG.
# ---------------------------------------------------------------------------
DEBUG_VERBOSE = 5
logging.addLevelName(DEBUG_VERBOSE, 'DEBUG_VERBOSE')


# ---------------------------------------------------------------------------
# JSON formatter — one object per log record, machine-parseable.
# ---------------------------------------------------------------------------

# Standard LogRecord attributes that are always set by the logging module;
# anything NOT in this set was added by the caller via ``extra=`` and should
# be included as a top-level JSON field.
_LOGRECORD_STANDARD_ATTRS = frozenset({
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
    'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
    'processName', 'process', 'message', 'asctime', 'taskName',
})


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    Always-present keys::

        timestamp   ISO 8601 with microseconds, UTC ('Z' suffix)
        level       'INFO' | 'WARNING' | 'ERROR' | 'DEBUG' | 'DEBUG_VERBOSE'
        logger      logger name, e.g. 'modena.strategy'
        message     the formatted message (after % / {} substitution)

    Any attributes attached via ``logger.info(..., extra={'model_id': 'x'})``
    are added as top-level keys.  ``exc_info`` and ``stack_info`` are
    serialised into an ``exception`` key when present.

    No external dependency — a small custom formatter is enough for the
    volume MoDeNa produces and lets ``jq`` do all downstream filtering.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            'timestamp': datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec='microseconds').replace('+00:00', 'Z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        # Merge in caller-supplied extras (anything not in the standard set).
        for k, v in record.__dict__.items():
            if k in _LOGRECORD_STANDARD_ATTRS or k.startswith('_'):
                continue
            try:
                json.dumps(v)   # cheap serialisability probe
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)

        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        if record.stack_info:
            payload['stack'] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)

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


def configure_logging(
    level: str = 'INFO',
    file: str = None,
    fmt: str = 'text',
) -> None:
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
        If given, also write all modena + FireWorks messages to this file.
        The file is opened in append mode.  Format is controlled by ``fmt``.
    fmt : str
        File format: ``'text'`` (default) or ``'json'``.  ``'text'`` writes
        one human-readable line per record with a timestamp prefix; ``'json'``
        writes one JSON object per record with any caller-supplied ``extra=``
        fields promoted to top-level keys.  Ignored when ``file`` is None.
        Overridable via ``MODENA_LOG_FORMAT`` environment variable.
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
        effective_fmt = os.environ.get('MODENA_LOG_FORMAT', fmt).lower()
        _VALID_FMTS = {'text', 'json'}
        if effective_fmt not in _VALID_FMTS:
            logger.warning(
                "Unrecognised log format %r — falling back to 'text'. "
                "Valid values: %s",
                effective_fmt, ', '.join(sorted(_VALID_FMTS)),
            )
            effective_fmt = 'text'

        if effective_fmt == 'json':
            formatter: logging.Formatter = JsonFormatter()
        else:
            formatter = logging.Formatter(
                '%(asctime)s  %(levelname)-8s  %(name)s: %(message)s'
            )

        # Remove any existing FileHandlers added by a previous configure_logging()
        # call so that repeated calls don't accumulate duplicate handlers.
        for _log_name in ('modena', 'fireworks'):
            _lg = logging.getLogger(_log_name)
            for _h in list(_lg.handlers):
                if isinstance(_h, logging.FileHandler):
                    _lg.removeHandler(_h)
                    _h.close()

        fh = logging.FileHandler(file, mode='a')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logging.getLogger('fireworks').addHandler(fh)
        logging.getLogger('fireworks').setLevel(logging.DEBUG)
