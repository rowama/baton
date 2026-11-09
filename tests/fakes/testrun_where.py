"""Copied into a fixture repository by tests/test_testrun.py: where does `baton` come from, here and in a child?"""
import os
import subprocess
import sys

import baton

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_baton_comes_from_this_checkout():
    assert os.path.abspath(baton.__file__).startswith(os.path.join(ROOT, "src"))


def test_a_child_with_a_bare_environment_sees_the_same_baton():
    out = subprocess.run([sys.executable, "-c", "import baton;print(baton.__file__)"], capture_output=True, text=True,
                         env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
    assert os.path.abspath(out.stdout.strip()).startswith(os.path.join(ROOT, "src")), out
