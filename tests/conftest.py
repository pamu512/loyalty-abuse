import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Existing API regression tests run with auth disabled; auth contract tests
# explicitly clear this flag. Production never sets LOYALTY_ABUSE_AUTH_DISABLED.
os.environ.setdefault("LOYALTY_ABUSE_AUTH_DISABLED", "true")
