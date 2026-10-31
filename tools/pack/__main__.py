# The pack's build, crises first: uv run python -m tools.pack

from tools.pack import compute, crises

crises.main()
compute.main()
