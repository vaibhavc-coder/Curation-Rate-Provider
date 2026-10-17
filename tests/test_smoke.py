"""Initial smoke test to verify test harness and environment."""

import sys
from ptd.config import load_config
from ptd.io_utils import get_ijson_backend_info


def test_environment_smoke():
    assert sys.version_info >= (3, 11), "Python 3.11+ required"
    config = load_config()
    assert config.project_root.exists()
    assert config.raw_dir.exists()
    assert config.index_dir.exists()


def test_ijson_backend_active():
    info = get_ijson_backend_info()
    assert info["active_backend"] in ("yajl2_c", "yajl2", "yajl2_cffi"), (
        f"Fast backend expected, got {info['active_backend']}"
    )
