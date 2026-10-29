# uv run fiam <verb> runs this folder; uv run fiam help lists the verbs.

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The root replaces this folder on the path, so fiam is a package.
sys.path[:] = [str(ROOT), *(p for p in sys.path if Path(p or ".").resolve() != ROOT / "fiam")]

from fiam.vfinal import cli  # noqa: E402

# The verb and its arguments, with the exit code passed back.
if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]))
