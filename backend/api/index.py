import sys
import os
from pathlib import Path

# Ensure the backend project root (where config/ and trips/ live) is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application  # noqa: E402

app = application
