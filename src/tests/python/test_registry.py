"""
Tests for modena.Registry
--------------------------
Covers:
  - _load_toml             missing file, valid file
  - _find_project_config   walks up directory tree correctly
  - _write_toml_minimal    round-trip, special characters, nested dicts
  - _read_dist_info        valid METADATA, missing directory
  - ModelRegistry.load     MODENA_PATH env var, de-duplication
  - ModelRegistry          singleton behaviour
  - ModelRegistry.restore  verify_only reports mismatches without writing DB

None of these tests require MongoDB.  The restore() test uses verify_only=True
so it never touches the database.
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# _load_toml
# ---------------------------------------------------------------------------

class TestLoadToml:

    def test_missing_file_returns_empty(self):
        from modena.Registry import _load_toml
        assert _load_toml('/nonexistent/path/modena.lock') == {}

    def test_valid_file_returns_dict(self, tmp_path):
        from modena.Registry import _load_toml
        lock = tmp_path / 'modena.lock'
        lock.write_text('[meta]\nversion = "1.0"\n', encoding='utf-8')
        data = _load_toml(lock)
        assert data.get('meta', {}).get('version') == '1.0'

    def test_directory_returns_empty(self, tmp_path):
        from modena.Registry import _load_toml
        assert _load_toml(tmp_path) == {}


# ---------------------------------------------------------------------------
# _write_toml_minimal / round-trip
# ---------------------------------------------------------------------------

class TestWriteTomlMinimal:

    def test_round_trip_flat(self, tmp_path):
        from modena.Registry import _write_toml_minimal, _load_toml
        data = {'key': 'value', 'n': 42, 'f': 3.14}
        path = tmp_path / 'test.toml'
        _write_toml_minimal(path, data)
        loaded = _load_toml(path)
        assert loaded['key'] == 'value'
        assert loaded['n'] == 42

    def test_round_trip_nested(self, tmp_path):
        from modena.Registry import _write_toml_minimal, _load_toml
        data = {
            'meta': {'version': '1.0', 'generated': '2026-01-01T00:00:00'},
            'packages': {'flowRate': '1.0'},
            'models': {
                'flowRate': {
                    'n_samples': 42,
                    'parameters': [1.0, 2.0, 3.0],
                }
            },
        }
        path = tmp_path / 'modena.lock'
        _write_toml_minimal(path, data)
        loaded = _load_toml(path)
        assert loaded['meta']['version'] == '1.0'
        assert loaded['packages']['flowRate'] == '1.0'
        assert loaded['models']['flowRate']['n_samples'] == 42
        assert loaded['models']['flowRate']['parameters'] == [1.0, 2.0, 3.0]

    def test_special_characters_in_string(self, tmp_path):
        from modena.Registry import _write_toml_minimal, _load_toml
        data = {'path': r'C:\Users\test "name"'}
        path = tmp_path / 'test.toml'
        _write_toml_minimal(path, data)
        loaded = _load_toml(path)
        assert loaded['path'] == r'C:\Users\test "name"'

    def test_boolean_values(self, tmp_path):
        from modena.Registry import _write_toml_minimal, _load_toml
        data = {'flag_on': True, 'flag_off': False}
        path = tmp_path / 'test.toml'
        _write_toml_minimal(path, data)
        loaded = _load_toml(path)
        assert loaded['flag_on'] is True
        assert loaded['flag_off'] is False

    def test_empty_list(self, tmp_path):
        from modena.Registry import _write_toml_minimal, _load_toml
        data = {'items': []}
        path = tmp_path / 'test.toml'
        _write_toml_minimal(path, data)
        loaded = _load_toml(path)
        assert loaded['items'] == []


# ---------------------------------------------------------------------------
# _read_dist_info
# ---------------------------------------------------------------------------

class TestReadDistInfo:

    def test_reads_metadata_file(self, tmp_path):
        from modena.Registry import _read_dist_info
        di = tmp_path / 'flowRate-1.2.3.dist-info'
        di.mkdir()
        (di / 'METADATA').write_text(
            'Metadata-Version: 2.1\nName: flowRate\nVersion: 1.2.3\n',
            encoding='utf-8',
        )
        name, version = _read_dist_info(str(di))
        assert name == 'flowRate'
        assert version == '1.2.3'

    def test_reads_pkg_info_fallback(self, tmp_path):
        from modena.Registry import _read_dist_info
        di = tmp_path / 'idealGas-0.1.dist-info'
        di.mkdir()
        (di / 'PKG-INFO').write_text(
            'Name: idealGas\nVersion: 0.1\n', encoding='utf-8'
        )
        name, version = _read_dist_info(str(di))
        assert name == 'idealGas'
        assert version == '0.1'

    def test_missing_directory_returns_none(self):
        from modena.Registry import _read_dist_info
        name, version = _read_dist_info('/nonexistent/dir.dist-info')
        assert name is None
        assert version is None

    def test_empty_directory_returns_none(self, tmp_path):
        from modena.Registry import _read_dist_info
        di = tmp_path / 'empty.dist-info'
        di.mkdir()
        name, version = _read_dist_info(str(di))
        assert name is None
        assert version is None


# ---------------------------------------------------------------------------
# _find_project_config
# ---------------------------------------------------------------------------

class TestFindProjectConfig:

    def test_finds_config_in_current_dir(self, tmp_path, monkeypatch):
        from modena.Registry import _find_project_config
        (tmp_path / 'modena.toml').write_text('[models]\npaths = []\n')
        monkeypatch.chdir(tmp_path)
        found = _find_project_config()
        assert found == tmp_path / 'modena.toml'

    def test_finds_config_in_ancestor(self, tmp_path, monkeypatch):
        from modena.Registry import _find_project_config
        (tmp_path / 'modena.toml').write_text('')
        subdir = tmp_path / 'a' / 'b' / 'c'
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        found = _find_project_config()
        assert found == tmp_path / 'modena.toml'

    def test_returns_none_when_not_found(self, tmp_path, monkeypatch):
        from modena.Registry import _find_project_config
        monkeypatch.chdir(tmp_path)
        # Ensure no modena.toml exists anywhere above tmp_path up to root.
        # We can't guarantee the filesystem, so just check the function doesn't crash.
        result = _find_project_config()
        # If a modena.toml happens to exist above tmp_path, accept it.
        assert result is None or result.name == 'modena.toml'


# ---------------------------------------------------------------------------
# ModelRegistry — singleton
# ---------------------------------------------------------------------------

class TestModelRegistrySingleton:

    def setup_method(self):
        # Reset the singleton before each test
        from modena.Registry import ModelRegistry
        ModelRegistry._instance = None

    def test_same_instance_returned_twice(self):
        from modena.Registry import ModelRegistry
        a = ModelRegistry()
        b = ModelRegistry()
        assert a is b

    def test_load_picks_up_modena_path(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        monkeypatch.setenv('MODENA_PATH', str(tmp_path))
        monkeypatch.delenv('MODENA_SURROGATE_LIB_DIR', raising=False)
        reg = ModelRegistry()
        reg.load()
        assert str(tmp_path.resolve()) in reg._prefixes

    def test_load_deduplicates_paths(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        p = str(tmp_path)
        monkeypatch.setenv('MODENA_PATH', f'{p}:{p}:{p}')
        reg = ModelRegistry()
        reg.load()
        assert reg._prefixes.count(str(tmp_path.resolve())) == 1

    def test_surrogate_lib_dir_default(self):
        from modena.Registry import ModelRegistry
        reg = ModelRegistry()
        reg._surrogate_lib_dir = None
        expected = Path.home() / '.modena' / 'surrogate_functions'
        assert reg.surrogate_lib_dir == expected

    def test_surrogate_lib_dir_dot_returns_cwd(self):
        from modena.Registry import ModelRegistry
        reg = ModelRegistry()
        reg._surrogate_lib_dir = '.'
        assert reg.surrogate_lib_dir == Path.cwd()


# ---------------------------------------------------------------------------
# ModelRegistry.restore — verify_only (no MongoDB access)
# ---------------------------------------------------------------------------

class TestRegistryRestoreVerifyOnly:

    def setup_method(self):
        from modena.Registry import ModelRegistry
        ModelRegistry._instance = None

    def test_version_match_logs_ok(self, tmp_path, caplog):
        import logging
        from modena.Registry import ModelRegistry, _write_toml_minimal
        reg = ModelRegistry()
        reg._packages = {'flowRate': '1.0'}
        with patch.object(reg, 'active_packages', return_value={'flowRate': '1.0'}):
            lock = tmp_path / 'modena.lock'
            _write_toml_minimal(lock, {
                'meta': {'modena_version': '1.0', 'generated': '2026-01-01'},
                'packages': {'flowRate': '1.0'},
                'models': {},
            })
            with caplog.at_level(logging.INFO, logger='modena.registry'):
                reg.restore(lock, verify_only=True)
        assert any('match' in r.message.lower() for r in caplog.records)

    def test_version_mismatch_logs_warning(self, tmp_path, caplog):
        import logging
        from modena.Registry import ModelRegistry, _write_toml_minimal
        reg = ModelRegistry()
        with patch.object(reg, 'active_packages', return_value={'flowRate': '0.9'}):
            lock = tmp_path / 'modena.lock'
            _write_toml_minimal(lock, {
                'meta': {'modena_version': '1.0', 'generated': '2026-01-01'},
                'packages': {'flowRate': '1.0'},
                'models': {},
            })
            with caplog.at_level(logging.WARNING, logger='modena.registry'):
                reg.restore(lock, verify_only=True)
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_missing_lock_logs_message(self, tmp_path, caplog):
        import logging
        from modena.Registry import ModelRegistry
        reg = ModelRegistry()
        with caplog.at_level(logging.INFO, logger='modena.registry'):
            reg.restore(tmp_path / 'nonexistent.lock', verify_only=True)
        assert any('lock' in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# ModelRegistry.load — [logging] section in modena.toml
# ---------------------------------------------------------------------------

class TestRegistryLoggingConfig:

    def setup_method(self):
        from modena.Registry import ModelRegistry
        ModelRegistry._instance = None

    def test_toml_log_level_stored(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        (tmp_path / 'modena.toml').write_text(
            '[models]\npaths = []\n\n[logging]\nlevel = "WARNING"\n'
        )
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg._toml_log_level == 'WARNING'

    def test_toml_log_file_stored(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        (tmp_path / 'modena.toml').write_text(
            '[models]\npaths = []\n\n[logging]\nlevel = "DEBUG"\nfile = "run.log"\n'
        )
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg._toml_log_level == 'DEBUG'
        assert reg._toml_log_file == 'run.log'

    def test_no_logging_section_leaves_none(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        (tmp_path / 'modena.toml').write_text('[models]\npaths = []\n')
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg._toml_log_level is None
        assert reg._toml_log_file is None

    def test_level_uppercased(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        (tmp_path / 'modena.toml').write_text(
            '[models]\npaths = []\n\n[logging]\nlevel = "warning"\n'
        )
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg._toml_log_level == 'WARNING'


# ---------------------------------------------------------------------------
# ModelRegistry.active_packages — auto-import
# ---------------------------------------------------------------------------

class TestActivePackages:

    def setup_method(self):
        from modena.Registry import ModelRegistry
        ModelRegistry._instance = None

    def test_returns_empty_when_no_prefixes(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_PATH', raising=False)
        reg = ModelRegistry().load()
        pkgs = reg.active_packages()
        assert isinstance(pkgs, dict)

    def test_finds_package_in_registered_prefix(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry, _site_packages_in_prefix
        import glob
        # Build a fake dist-info tree under tmp_path
        sp = tmp_path / 'lib' / 'python3.10' / 'site-packages'
        sp.mkdir(parents=True)
        di = sp / 'myModel-1.0.dist-info'
        di.mkdir()
        (di / 'METADATA').write_text(
            'Metadata-Version: 2.1\nName: myModel\nVersion: 1.0\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('MODENA_PATH', str(tmp_path))
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        pkgs = reg.active_packages()
        assert 'myModel' in pkgs
        assert pkgs['myModel'] == '1.0'

    def test_auto_import_succeeds(self, tmp_path, monkeypatch):
        """active_packages() returns a package that can be imported via sys.modules stub."""
        import sys
        import types
        from modena.Registry import ModelRegistry

        # Install a fake module into sys.modules before active_packages is called
        fake_mod = types.ModuleType('fakeModel')
        monkeypatch.setitem(sys.modules, 'fakeModel', fake_mod)

        # Build dist-info so active_packages() discovers it
        sp = tmp_path / 'lib' / 'python3.10' / 'site-packages'
        sp.mkdir(parents=True)
        di = sp / 'fakeModel-2.0.dist-info'
        di.mkdir()
        (di / 'METADATA').write_text(
            'Name: fakeModel\nVersion: 2.0\n', encoding='utf-8'
        )
        monkeypatch.setenv('MODENA_PATH', str(tmp_path))
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        pkgs = reg.active_packages()
        assert 'fakeModel' in pkgs

        # Now verify that importlib.import_module would succeed (it's already in sys.modules)
        import importlib
        mod = importlib.import_module('fakeModel')
        assert mod is fake_mod

    def test_auto_import_silent_on_missing_package(self, tmp_path, monkeypatch):
        """active_packages() may list a package whose import fails — no exception raised."""
        import importlib
        from modena.Registry import ModelRegistry

        sp = tmp_path / 'lib' / 'python3.10' / 'site-packages'
        sp.mkdir(parents=True)
        di = sp / 'ghostPkg-1.0.dist-info'
        di.mkdir()
        (di / 'METADATA').write_text(
            'Name: ghostPkg\nVersion: 1.0\n', encoding='utf-8'
        )
        monkeypatch.setenv('MODENA_PATH', str(tmp_path))
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        pkgs = reg.active_packages()
        assert 'ghostPkg' in pkgs

        # Import should raise ImportError (package not actually installed)
        with pytest.raises(ImportError):
            importlib.import_module('ghostPkg')


# ---------------------------------------------------------------------------
# ModelRegistry.bin_search_path / find_binary
# ---------------------------------------------------------------------------

class TestBinSearchPath:

    def setup_method(self):
        from modena.Registry import ModelRegistry
        ModelRegistry._instance = None

    def test_empty_by_default(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_BIN_PATH', raising=False)
        reg = ModelRegistry().load()
        assert reg.bin_search_path == []

    def test_modena_bin_path_env_var(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        d1 = tmp_path / 'bin1'
        d2 = tmp_path / 'bin2'
        d1.mkdir(); d2.mkdir()
        monkeypatch.setenv('MODENA_BIN_PATH', f'{d1}:{d2}')
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert str(d1.resolve()) in reg.bin_search_path
        assert str(d2.resolve()) in reg.bin_search_path

    def test_modena_bin_path_deduplicates(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        d = tmp_path / 'bin'
        d.mkdir()
        monkeypatch.setenv('MODENA_BIN_PATH', f'{d}:{d}:{d}')
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        assert reg.bin_search_path.count(str(d.resolve())) == 1

    def test_toml_binaries_paths(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        bin_dir = tmp_path / 'mybins'
        bin_dir.mkdir()
        (tmp_path / 'modena.toml').write_text(
            f'[binaries]\npaths = ["{bin_dir}"]\n'
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_BIN_PATH', raising=False)
        reg = ModelRegistry().load()
        assert str(bin_dir.resolve()) in reg.bin_search_path

    def test_env_var_appended_after_toml(self, tmp_path, monkeypatch):
        """MODENA_BIN_PATH entries appear after [binaries] paths from toml."""
        from modena.Registry import ModelRegistry
        toml_bin = tmp_path / 'toml_bin'
        env_bin  = tmp_path / 'env_bin'
        toml_bin.mkdir(); env_bin.mkdir()
        (tmp_path / 'modena.toml').write_text(
            f'[binaries]\npaths = ["{toml_bin}"]\n'
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv('MODENA_BIN_PATH', str(env_bin))
        reg = ModelRegistry().load()
        path = reg.bin_search_path
        assert path.index(str(toml_bin.resolve())) < path.index(str(env_bin.resolve()))

    def test_find_binary_in_configured_dir(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        binary = bin_dir / 'myExact'
        binary.write_text('#!/bin/sh\n')
        monkeypatch.setenv('MODENA_BIN_PATH', str(bin_dir))
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        found = reg.find_binary('myExact')
        assert found == str(binary.resolve())

    def test_find_binary_package_relative_fallback(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        # Simulate a model package: /tmp/pkg/myModel.py beside /tmp/pkg/bin/myExact
        pkg_dir = tmp_path / 'pkg'
        bin_dir = pkg_dir / 'bin'
        bin_dir.mkdir(parents=True)
        caller_file = pkg_dir / 'myModel.py'
        caller_file.write_text('')
        binary = bin_dir / 'myExact'
        binary.write_text('#!/bin/sh\n')
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_BIN_PATH', raising=False)
        reg = ModelRegistry().load()
        found = reg.find_binary('myExact', caller_file=str(caller_file))
        assert found == str(binary.resolve())

    def test_find_binary_configured_path_takes_precedence_over_fallback(
        self, tmp_path, monkeypatch
    ):
        from modena.Registry import ModelRegistry
        # Two binaries with the same name in different locations
        configured_bin = tmp_path / 'configured'
        pkg_bin = tmp_path / 'pkg' / 'bin'
        configured_bin.mkdir(); pkg_bin.mkdir(parents=True)
        (configured_bin / 'myExact').write_text('configured')
        (pkg_bin / 'myExact').write_text('package')
        caller_file = tmp_path / 'pkg' / 'myModel.py'
        caller_file.write_text('')
        monkeypatch.setenv('MODENA_BIN_PATH', str(configured_bin))
        monkeypatch.chdir(tmp_path)
        reg = ModelRegistry().load()
        found = reg.find_binary('myExact', caller_file=str(caller_file))
        assert (configured_bin / 'myExact').read_text() == 'configured'
        assert found == str((configured_bin / 'myExact').resolve())

    def test_find_binary_raises_when_not_found(self, tmp_path, monkeypatch):
        from modena.Registry import ModelRegistry
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_BIN_PATH', raising=False)
        reg = ModelRegistry().load()
        with pytest.raises(FileNotFoundError, match='nonexistent_binary'):
            reg.find_binary('nonexistent_binary')

    def test_find_binary_raises_with_caller_file_when_not_found(
        self, tmp_path, monkeypatch
    ):
        from modena.Registry import ModelRegistry
        caller_file = tmp_path / 'myModel.py'
        caller_file.write_text('')
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_BIN_PATH', raising=False)
        reg = ModelRegistry().load()
        with pytest.raises(FileNotFoundError, match='ghost'):
            reg.find_binary('ghost', caller_file=str(caller_file))
