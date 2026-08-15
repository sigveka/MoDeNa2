"""
Tests for modena._logging — JSON formatter, format toggle, extras.
"""

import json
import logging

import pytest


# ---------------------------------------------------------------------------
# JsonFormatter — record shape
# ---------------------------------------------------------------------------

class TestJsonFormatter:
    """The formatter must emit one JSON object per record with fixed keys
    plus any caller-supplied ``extra=`` fields promoted to top-level keys."""

    def _make_record(self, **kwargs) -> logging.LogRecord:
        logger = logging.getLogger('modena.tests.jsonfmt')
        return logger.makeRecord(
            name=kwargs.pop('name', 'modena.tests.jsonfmt'),
            level=kwargs.pop('level', logging.INFO),
            fn=kwargs.pop('fn', 'test.py'),
            lno=kwargs.pop('lno', 1),
            msg=kwargs.pop('msg', 'hello'),
            args=kwargs.pop('args', ()),
            exc_info=kwargs.pop('exc_info', None),
            func=kwargs.pop('func', None),
            extra=kwargs.pop('extra', None),
            sinfo=kwargs.pop('sinfo', None),
        )

    def test_output_is_valid_json(self):
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()
        record = self._make_record()
        out = fmt.format(record)
        payload = json.loads(out)
        assert isinstance(payload, dict)

    def test_always_present_keys(self):
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()
        record = self._make_record(msg='hi')
        payload = json.loads(fmt.format(record))
        assert set(payload) >= {'timestamp', 'level', 'logger', 'message'}
        assert payload['level'] == 'INFO'
        assert payload['logger'] == 'modena.tests.jsonfmt'
        assert payload['message'] == 'hi'

    def test_timestamp_is_iso_utc(self):
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()
        payload = json.loads(fmt.format(self._make_record()))
        # ISO 8601 with Z suffix (UTC)
        assert payload['timestamp'].endswith('Z')
        assert 'T' in payload['timestamp']

    def test_extras_promoted_to_top_level(self):
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()
        record = self._make_record(
            extra={'model_id': 'flowRate', 'return_code': 202},
        )
        payload = json.loads(fmt.format(record))
        assert payload['model_id'] == 'flowRate'
        assert payload['return_code'] == 202

    def test_message_substitution_applied(self):
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()
        record = self._make_record(msg='rc=%d', args=(200,))
        payload = json.loads(fmt.format(record))
        assert payload['message'] == 'rc=200'

    def test_unserialisable_extra_falls_back_to_repr(self):
        """An object that json can't serialise must not crash the formatter."""
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()

        class NotSerialisable:
            def __repr__(self):
                return '<NotSerialisable>'

        record = self._make_record(extra={'weird': NotSerialisable()})
        payload = json.loads(fmt.format(record))
        assert payload['weird'] == '<NotSerialisable>'

    def test_standard_logrecord_attrs_not_leaked(self):
        """Fields like 'levelname', 'name', 'process' must not appear as
        top-level keys — they'd duplicate 'level' and 'logger'."""
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()
        payload = json.loads(fmt.format(self._make_record()))
        for hidden in ('levelname', 'name', 'process', 'thread', 'msecs'):
            assert hidden not in payload

    def test_exception_serialised(self):
        from modena._logging import JsonFormatter
        fmt = JsonFormatter()
        try:
            raise ValueError('boom')
        except ValueError:
            import sys as _sys
            record = self._make_record(exc_info=_sys.exc_info())
        payload = json.loads(fmt.format(record))
        assert 'exception' in payload
        assert 'ValueError' in payload['exception']
        assert 'boom' in payload['exception']


# ---------------------------------------------------------------------------
# configure_logging — fmt='json' end to end via a FileHandler
# ---------------------------------------------------------------------------

class TestConfigureLoggingFmt:
    """``configure_logging(file=..., fmt='json')`` must attach a
    ``JsonFormatter`` to the FileHandler; ``fmt='text'`` must keep the
    legacy timestamped formatter."""

    def test_json_fmt_writes_valid_json_lines(self, tmp_path):
        from modena._logging import configure_logging, JsonFormatter
        log = logging.getLogger('modena.tests.cfg_json')
        log_file = tmp_path / 'events.jsonl'
        configure_logging(level='INFO', file=str(log_file), fmt='json')
        try:
            log.info('a message', extra={'model_id': 'flowRate'})
            log.error('rc=%d', 200, extra={'return_code': 200})
            # Flush & remove file handlers so caplog fixtures are unaffected.
            for h in list(logging.getLogger('modena').handlers):
                if isinstance(h, logging.FileHandler):
                    h.flush()
        finally:
            # Cleanup: strip added file handlers so subsequent tests aren't
            # writing to tmp files that no longer exist.
            for lname in ('modena', 'fireworks'):
                lg = logging.getLogger(lname)
                for h in list(lg.handlers):
                    if isinstance(h, logging.FileHandler):
                        lg.removeHandler(h)
                        h.close()

        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        # Every line must be a JSON object
        payloads = [json.loads(ln) for ln in lines]
        # And at least one of them carries the extras we asked for
        assert any(p.get('model_id') == 'flowRate' for p in payloads)
        assert any(p.get('return_code') == 200 for p in payloads)

    def test_text_fmt_keeps_legacy_format(self, tmp_path):
        from modena._logging import configure_logging
        log = logging.getLogger('modena.tests.cfg_text')
        log_file = tmp_path / 'run.log'
        configure_logging(level='INFO', file=str(log_file), fmt='text')
        try:
            log.info('a message')
            for h in list(logging.getLogger('modena').handlers):
                if isinstance(h, logging.FileHandler):
                    h.flush()
        finally:
            for lname in ('modena', 'fireworks'):
                lg = logging.getLogger(lname)
                for h in list(lg.handlers):
                    if isinstance(h, logging.FileHandler):
                        lg.removeHandler(h)
                        h.close()

        content = log_file.read_text()
        assert 'a message' in content
        # Text format contains the level name and logger name inline
        assert 'INFO' in content
        assert 'modena.tests.cfg_text' in content
        # And it is NOT valid JSON per line
        with pytest.raises(json.JSONDecodeError):
            json.loads(content.splitlines()[0])

    def test_invalid_fmt_falls_back_to_text(self, tmp_path):
        from modena._logging import configure_logging
        log = logging.getLogger('modena.tests.cfg_bad')
        log_file = tmp_path / 'run.log'
        configure_logging(level='INFO', file=str(log_file), fmt='xml')
        try:
            log.info('a message')
            for h in list(logging.getLogger('modena').handlers):
                if isinstance(h, logging.FileHandler):
                    h.flush()
        finally:
            for lname in ('modena', 'fireworks'):
                lg = logging.getLogger(lname)
                for h in list(lg.handlers):
                    if isinstance(h, logging.FileHandler):
                        lg.removeHandler(h)
                        h.close()
        # Fallback = text format
        assert 'a message' in log_file.read_text()

    def test_env_var_overrides_fmt_argument(self, tmp_path, monkeypatch):
        from modena._logging import configure_logging
        log = logging.getLogger('modena.tests.cfg_env')
        log_file = tmp_path / 'run.log'
        monkeypatch.setenv('MODENA_LOG_FORMAT', 'json')
        # Pass fmt='text' — env var must win
        configure_logging(level='INFO', file=str(log_file), fmt='text')
        try:
            log.info('hi', extra={'model_id': 'x'})
            for h in list(logging.getLogger('modena').handlers):
                if isinstance(h, logging.FileHandler):
                    h.flush()
        finally:
            for lname in ('modena', 'fireworks'):
                lg = logging.getLogger(lname)
                for h in list(lg.handlers):
                    if isinstance(h, logging.FileHandler):
                        lg.removeHandler(h)
                        h.close()
        payload = json.loads(log_file.read_text().splitlines()[0])
        assert payload['model_id'] == 'x'


# ---------------------------------------------------------------------------
# Registry.load — [logging] format key
# ---------------------------------------------------------------------------

class TestRegistryLoggingFormatConfig:

    def setup_method(self):
        from modena.Registry import ModelRegistry
        ModelRegistry._instance = None

    def test_toml_log_format_stored(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        (tmp_path / 'modena.toml').write_text(
            '[models]\npaths = []\n\n'
            '[logging]\nlevel = "DEBUG"\nfile = "run.log"\nformat = "json"\n'
        )
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg._toml_log_format == 'json'

    def test_missing_format_key_leaves_none(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        (tmp_path / 'modena.toml').write_text(
            '[models]\npaths = []\n\n[logging]\nlevel = "INFO"\n'
        )
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg._toml_log_format is None

    def test_format_key_lowercased(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        (tmp_path / 'modena.toml').write_text(
            '[models]\npaths = []\n\n[logging]\nformat = "JSON"\n'
        )
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg._toml_log_format == 'json'
