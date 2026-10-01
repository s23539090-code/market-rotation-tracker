# Market Rotation Tracker

Which crypto sector the market is actually rotating into right now — built on
[CoinGecko API](https://www.coingecko.com/en/api?utm_source=x&utm_content=Okada_DeFi0x)
data, by [@Okada_DeFi0x](https://x.com/Okada_DeFi0x).

A sector "pumping" on raw 24h volume isn't the same as money actually rotating
into it — volume alone doesn't prove net inflow. This tracker combines three
layers before calling something a rotation:

1. **Relative strength** — each sector's return vs. ETH (not just its raw %),
   across 24h / 7d / 30d, cap-weighted and median.
2. **Breadth** — what share of the sector's tokens are *individually* beating
   ETH, so one pumping token can't fake a whole-sector move.
3. **Onchain check** — DEX buy/sell flow and holder growth on each sector's
   top movers' most active pool, as a closer proxy for real accumulation than
   trading volume on its own.

Sectors are plotted on a rotation map (trend × momentum, four quadrants:
Leading / Improving / Weakening / Lagging) and ranked by a composite rotation
score. Live dashboard updates hourly via GitHub Actions + GitHub Pages — no
server to run.

## What's from CoinGecko, and what's ours

Prices, market caps, trading volume, DEX pool activity and holder counts are
raw [CoinGecko API](https://www.coingecko.com/en/api?utm_source=x&utm_content=Okada_DeFi0x)
fields. The rotation score, the quadrant labels, relative-strength and
breadth numbers are **computed by this repo's own code** from that data —
they are not official CoinGecko classifications, signals, or financial
advice. See [`docs/api-verification.md`](docs/api-verification.md) for the
exact field-by-field mapping.

## Quick start

```bash
git clone https://github.com/s23539090-code/market-rotation-tracker.git
cd market-rotation-tracker
cp .env.example .env        # then paste your API key into .env
python run.py check         # validates config without calling the API
python run.py demo          # runs the full pipeline on simulated data — no key needed
python run.py collect       # one real run against the CoinGecko API
```

Open `docs/index.html` in a local server (`python -m http.server --directory docs`)
to preview the dashboard, or just push to GitHub and turn on Pages (see
[`docs/SETUP.md`](docs/SETUP.md) for the full click-by-click guide, in
Vietnamese).

### Getting an API key

1. Sign up for a free [CoinGecko Demo account](https://www.coingecko.com/en/api?utm_source=x&utm_content=Okada_DeFi0x).
2. Send the email you signed up with to Brian (brian.lee@coingecko.com /
   [@blshwpp](https://t.me/blshwpp) on Telegram) for an Analyst-plan upgrade.
3. Generate a new key after the upgrade (a paid key needs `pro-api.coingecko.com`,
   a fresh key avoids a stale-environment mismatch).
4. Put it in `.env` locally, and as a `COINGECKO_API_KEY` **repository
   secret** for the GitHub Actions workflow — never in code, a commit, or a
   screenshot.

## Running on a schedule (GitHub Actions)

`.github/workflows/hourly.yml` runs `python run.py collect` every hour,
commits the updated JSON under `docs/data/`, and GitHub Pages serves the
dashboard straight from that folder. Set these repo secrets under
**Settings → Secrets and variables → Actions**:

| Secret | Required | Value |
|---|---|---|
| `COINGECKO_API_KEY` | yes | your key |
| `COINGECKO_ENVIRONMENT` | no (defaults to `pro`) | `pro` or `demo` |

## Project layout

```
rotation/
  client.py     CoinGecko API client (stdlib only, retries, never logs the key)
  collector.py  pulls markets per sector + benchmark, orchestrates one run
  metrics.py    relative strength, breadth, turnover, quadrant, rotation score
  onchain.py    Layer 3: DEX buy/sell flow + holder growth verification
  storage.py    append-only snapshots -> docs/data/*.json (what GitHub Pages serves)
  alerts.py     quadrant-change / breadth-jump / volume-surge detection
  mock_client.py  fixture client for `run.py demo` — same response shapes as the real API
config/sectors.json   which sectors to track, universe filters, score weights
docs/index.html       the dashboard (static, reads docs/data/*.json)
docs/SETUP.md         Vietnamese step-by-step setup guide
docs/api-verification.md   CoinGecko field-by-field reference used while building this
tests/                unit tests for the metrics engine
```

## Configuration

Edit `config/sectors.json` to change which sectors are tracked (any
[CoinGecko category id](https://docs.coingecko.com/reference/coins-categories-list)),
the universe filters (min market cap/volume, excluded stablecoins/wrapped
tokens), and the rotation-score weights.

## Links

- [CoinGecko API](https://www.coingecko.com/en/api?utm_source=x&utm_content=Okada_DeFi0x)
- [Pricing](https://www.coingecko.com/en/api/pricing?utm_source=x&utm_content=Okada_DeFi0x)
- [API docs](https://docs.coingecko.com?utm_source=x&utm_content=Okada_DeFi0x)

## Disclaimer

This is a research/educational tool, not financial advice. Rotation scores
and quadrant labels are examples of logic computed by this repo from raw
CoinGecko API data — inspect the underlying numbers before acting on them.
