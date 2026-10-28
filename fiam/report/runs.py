# The saved research runs: their fund sizes and the chosen book's name.

from fiam.paths import ARCHIVE
from fiam.paths import read_json as load

# Fund sizes every research book ran at.
CAPITALS = (1e6, 1e7, 1e8, 5e8, 1e9, 5e9)


# The chosen research book's run folder at one fund size.
def final_run(capital: float = 1e7) -> str:
    name = load(ARCHIVE / "evidence.json")["v3"]["final"]["name"]
    return f"{name}@{capital:.0e}".replace("+0", "")
