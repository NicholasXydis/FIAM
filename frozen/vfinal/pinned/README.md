# Pinned results of the original pipeline

The build reads these two files and never writes them. Each is hashed in `frozen/vfinal/vfinal.sha256` and in `inputs.json`.

| File | What it holds | Made by | Hash proof |
|---|---|---|---|
| `validate_9f47207c568b.json` | The SUE model's cell (leaves and minimum children) for the el_plus SUE forecast, chosen on 2019 to 2020 before the unseal | The original pipeline, `python -m fiam.vfinal.forecast.grid validate` at commit 9f47207c568b | sha256 2821420008dc… listed in the old lock `frozen/vfinal/vfinal.sha256` at commit e761c15 |
| `spread_ratios.json` | The half-spread ratio by size group, from TAQ 2015 to 2020 | `fiam/vfinal/construct/costs.py` `spread_ratios()` in blind mode on 2026-10-26, before the unseal. It regenerates byte for byte in blind mode. With the gate open, rows public after 2020 move the ratios in the 4th digit, which is why the file is pinned | sha256 14663d3e… listed in `frozen/vfinal0/inputs.json` |

The validate file cannot be regenerated without the archived ensemble validation (`~/FIAM_work/archive/2026-10-28/vfinal_old/`). Only its `sue_model` choice is read.
