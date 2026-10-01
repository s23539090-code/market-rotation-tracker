# CoinGecko API field verification

Checked against docs.coingecko.com while building this repo (2026-10). This
is what `rotation/client.py`, `rotation/collector.py` and `rotation/onchain.py`
actually call and parse. If CoinGecko changes a response shape, this is the
file to recheck first.

## `GET /coins/markets`
Used for: sector universes (with `category=`) and the ETH/BTC benchmark (with `ids=`).

Params used: `vs_currency=usd`, `category`, `ids`, `order=volume_desc`,
`per_page`, `price_change_percentage=24h,7d,30d`, `sparkline=false`.

Fields used: `id`, `symbol`, `name`, `image`, `current_price`, `market_cap`,
`total_volume`, `price_change_percentage_24h_in_currency`,
`price_change_percentage_7d_in_currency`, `price_change_percentage_30d_in_currency`.

## `GET /coins/list?include_platform=true`
Used for: mapping a coin id to its onchain contract address(es), to feed the
onchain layer. Fields used: `id`, `platforms` (`{platform_id: address}`).

## `GET /onchain/networks/{network}/tokens/{token_address}/pools`
Used for: Layer 3 buy/sell flow, via `sort=h24_volume_usd_liquidity_desc`,
first result only. Fields used: `attributes.name`,
`attributes.transactions.h24.{buys,sells}`, `attributes.volume_usd.h24`,
`attributes.reserve_in_usd`.

Note: this endpoint gives transaction **counts**, not a buy/sell USD split —
`buy_share` here is `buys / (buys + sells)` by transaction count, an
approximation, not an exact USD-weighted buy share. Documented as such in the
dashboard's methodology note.

## `GET /onchain/networks/{network}/tokens/{token_address}/holders_chart?days=7`
Analyst plan and above; currently in Beta per CoinGecko's own docs. Fields
used: `data.attributes.token_holders_list` (array of `[timestamp, count]`
pairs) — we use first vs. last point for 7-day holder growth.

## `GET /coins/categories`
Not used directly for scoring (per-category snapshot has no history of its
own), but is how `config/sectors.json`'s `category` values are validated —
run `python run.py check` or see
[Coins Categories List](https://docs.coingecko.com/reference/coins-categories-list)
for valid ids.

## Auth

- Pro/Analyst key → `https://pro-api.coingecko.com/api/v3`, header
  `x-cg-pro-api-key`.
- Demo key → `https://api.coingecko.com/api/v3`, header `x-cg-demo-api-key`.
- A 401 almost always means `COINGECKO_ENVIRONMENT` doesn't match the key
  type — see the FAQ in CoinGecko's creator brief.
