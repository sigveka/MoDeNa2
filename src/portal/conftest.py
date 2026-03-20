"""
Pytest configuration for running portal tests from the source tree
without a full cmake --install.

Inserts the portal source directory into sys.modules under the
'modena_portal' name so that 'from modena_portal.x import y' resolves
to 'src/portal/x.py', matching what setup.py.in's package_dir mapping
produces after installation.
"""
import sys
import types
from pathlib import Path

_portal_src = Path(__file__).parent

# Only add the mapping if modena_portal isn't already installed.
if 'modena_portal' not in sys.modules:
    pkg = types.ModuleType('modena_portal')
    pkg.__path__ = [str(_portal_src)]
    pkg.__package__ = 'modena_portal'
    sys.modules['modena_portal'] = pkg
