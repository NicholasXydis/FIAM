# python -m fiam.vfinal run [stage ...] | verify | compare [folder]

import sys

# The command line runs only here, never in a worker's import.
if __name__ == "__main__":
    from fiam.vfinal import run

    sys.exit(run.main(sys.argv[1:]))
