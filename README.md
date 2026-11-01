# garmin-run-coach

A local-first running coach for the command line. It pulls your activities from Garmin Connect, builds a block-based training plan toward a race, checks the plan against what you actually ran, and adapts the next block.

Your Garmin data, API key and training history stay on your machine. The only thing that leaves it is the plan-generation prompt (see [How it works](#how-it-works)).

The methodology is grounded in running training literature and multi-year on-field experience. Every rule used by the validator carries a source reference in [`methodology.yaml`](methodology.yaml).

> **Language note:** the CLI messages, config comments and generated plans are currently in Italian. The code and this README are in English. Translations are welcome (see [Contributing](#contributing)).

## What it does

- **Sync**: incremental download of activities, daily health data and `.fit` files into a local SQLite database.
- **Plan**: generates a multi-week block from your goal, availability and fixed events, then validates it against explicit rules (hard sessions per week, long-run share, intensity distribution, deload weeks, taper). If the plan breaks a rule, it is regenerated.
- **Match & review**: pairs each planned session with the run you actually did, computes compliance and key-session hit rate, and applies adaptation rules.
- **Next block**: proposes the following block from the review (fixed recovery weeks, then progression).
- **Export**: writes the plan to an `.ics` calendar file you can import into Google Calendar, Apple Calendar, etc.
- **Feedback**: log RPE, how you felt and any pain after a session; it feeds the block review.

## Requirements

- Python 3.12+
- A Garmin Connect account and a [Garmin Personal API key](#getting-a-garmin-api-key)
- The [Claude Code CLI](https://claude.com/claude-code) (`claude`) on your `PATH`, used for plan generation (`plan-block`, `plan-next`). Everything else works without it.

## Install

```bash
git clone https://github.com/quokkasfriend/garmin-run-coach.git
cd garmin-run-coach
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env                 # add your Garmin API key
cp config.example.yaml config.yaml   # edit with your profile and race
```

### Getting a Garmin API key

Garmin Connect (web) → Settings → Personal API → Create key. Paste it in `.env` as `GARMIN_PERSONAL_API_KEY`. Keys expire after one year.

## Quick start

```bash
coach sync                 # pull your Garmin history
coach weeks                # weekly hours, km, D+ and Z3+ share (running only)
coach plan-block           # generate and validate a training block
coach export-ics           # export the block to data/blocks/*.ics

# as the block goes on
coach log --rpe 6 --feel buono --pain "left calf"
coach match                # planned vs. actual, compliance so far

# at the end of the block
coach review-block         # metrics + adaptation decision
coach plan-next            # next block, based on the review
```

Run `coach --help` or `coach <command> --help` for all options. `plan-block --dry-run` prints the prompt without calling Claude.

## Configuration

Everything about you lives in `config.yaml` (git-ignored). Start from [`config.example.yaml`](config.example.yaml), which contains a fictional athlete:

- `profile`: max and resting heart rate, a recent race result
- `goal`: target race, date and time
- `block`: start date, number of weeks, phase, per-week constraints
- `fixed_events`: races or sessions that must appear exactly as written
- `availability` / `strength`: run days per week, rest days, strength sessions
- `pinned_days`: days you have already decided, reproduced as-is
- `injuries`, `notes`: free-form constraints for the planner

## How it works

1. `coach sync` fills a local SQLite database from Garmin.
2. The planner builds a deterministic context (your recent load, config, methodology rules) and sends it to `claude -p`.
3. The returned block is parsed into typed models and checked by the validator. Violations are fed back and the block is regenerated, up to a retry limit.
4. Only blocks that pass validation are saved.

The LLM proposes; the rules decide. Anything the rules reject never reaches your calendar.

## Privacy

- `.env`, `config.yaml` and `data/` (token cache, database, `.fit` files) are git-ignored. Never commit them.
- `config.example.yaml` contains fictional data only.
- Plan generation sends your training context (from `config.yaml` and the local database) to Claude through the `claude` CLI. If that is not acceptable, use `--dry-run` and review the prompt, or skip LLM generation.

## Methodology

[`methodology.yaml`](methodology.yaml) holds the parameters used by the validator, each with its source (book and chapter) or flagged as a project default. The planner refuses to run if a value has no provenance. The books themselves are not included; if you own them, put them in `knowledge/books/` (git-ignored) for local reference.

The principles apply broadly to endurance running, but defaults are tuned for road races from 10k to the marathon. Review them against your own situation.

## Tests

```bash
pytest
```

Tests always run against `config.example.yaml`, never your personal config.

## Contributing

Issues and pull requests are welcome, especially for translations (English CLI output), other race distances, and additional data sources. Please keep personal data out of commits, fixtures and screenshots.

## Disclaimer

This is a planning tool, not medical or professional coaching advice. Listen to your body, and talk to a qualified professional before starting or changing a training program, especially if you have injuries or health conditions.

## License

[MIT](LICENSE)
