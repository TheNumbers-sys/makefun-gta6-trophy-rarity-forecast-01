[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/TheNumbers-sys/makefun-gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/TheNumbers-sys/makefun-gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

A standard-library Python forecaster for the [GTA VI trophy rarity bounty](https://make.fun/bounty/gta6-trophy-rarity-forecast-01). It reads case histories of Exophase page snapshots and writes five earn-rate quantiles per trophy for the case target.

## Run

```sh
MAKEFUN_INPUT_DIR=/path/to/cases MAKEFUN_OUTPUT_DIR=/path/to/output python3 main.py
```

The program processes every `.in` file in name order and writes a matching `.out` file. Without these variables it uses `/input` and `/output`.

## Model

Consecutive snapshots with the same player count and rates collapse into one epoch. The forecaster fits logit earn rates against the log of hours since launch, limits trend slopes by trophy tier, and projects tracked-player growth to estimate denominator dilution. When the history contains only one distinct epoch, a horizon-dependent refresh prior accounts for Exophase's delayed count updates. Quantile widths combine horizon uncertainty, fit residuals, and uncertainty from unseen refreshes; already saturated trophies receive a tight band near 100%.
