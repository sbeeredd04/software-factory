"""Ordinary Python process fixture for renderer SIGTERM cleanup; no browser calls."""
import importlib.util
import os
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("fixture_renderer", sys.argv[1])
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
child = "import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(20)"
renderer.run_child([sys.executable, "-c", child, sys.argv[2]], dict(os.environ), Path(sys.argv[3]), timeout=30)
