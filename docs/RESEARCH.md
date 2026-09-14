# FLY HIGH: реальный read-only research

## Запуск и интеграция

```sh
cd /root/projects/fly-high
python3 -m flyhigh.research --refresh
python3 -m flyhigh.research
python3 -m unittest discover -s tests -p test_research.py -v
```

`load_snapshot(path=None)` возвращает **только canonical DTO**, без сети. Его можно отдавать из `/api/research`. `refresh_snapshot(path=None)` делает пять публичных GET и возвращает тот же DTO. CLI принимает `--path`. Обновление запускается отдельно от pageview; рекомендуемая частота roster/PnL — не чаще раза в 15 минут. Модуль не меняет сервер, engine или web, не подключает кошелёк и не исполняет сделки.

По умолчанию файл `/root/projects/fly-high/data/research.snapshot.json` содержит envelope `{schema_version, refresh_attempted_at, raw, payload}`. В `raw` для каждого endpoint сохранены URL, timestamp, HTTP status, исходная JSON body, SHA-256 тела и распарсенные данные. `payload` — публичный DTO. Запись: временный файл в той же абсолютной директории, flush/fsync, atomic replace. Синтетические unit fixtures в production snapshot не попадают.

## Источники

Все запросы без ключей/оплаты, только `https://robinhoodtrenches.com`:

- `/api/traders?window=7d&stocks=false`
- `/api/tape?limit=500&stocks=false`
- `/api/closed?window=7d&stocks=false&limit=500`
- `/api/tokens?window=7d&stocks=false&limit=100`
- `/api/status`

`TrenchesClient`: urllib stdlib; честный User-Agent, JSON Accept, timeout по умолчанию 10 секунд, два повтора с bounded backoff (Retry-After ограничен 4 секундами), максимальное тело 8 MiB, in-process TTL 900 секунд. Некорректный JSON/схема не принимаются. MIME не используется как условие валидности. Явный refresh создаёт новый клиент и запрашивает сеть; cache повторных чтений приложения — файл snapshot.

При ошибке endpoint старый capture сохраняется с `stale=true` и исходным временем. Частичный результат допустим, пропуски и ошибки явно перечислены. Если файла нет/он повреждён, load возвращает пустой DTO с warning, без подмены реальных данных. `as_of` — последний fetch среди сохранённых источников, **не гарантия одновременности или свежести всех endpoint**: UI должен читать `coverage.endpoints.*.fetched_at/stale`. CLI возвращает ненулевой код при missing endpoints.

## Контракт

```text
{
  as_of: ISO-8601 UTC | null,
  source: {name, url, chain_id:4663, attribution, receipt_verified:false},
  window: "7d",
  coverage: {stocks:false, complete_history:false, since, until,
             tape_limit:500, closed_limit:500, token_limit:100,
             tape_window, endpoints:{...}, missing_endpoints:[]},
  wallets: [{address, handle, realized_pnl, unrealized_pnl, net_pnl,
             fills, win_rate, chain_id, identity_source, identity_verified:false,
             rules:{status, mapped_genes, reason, method, analysis, indexer_fill_count}, ...}],
  fills: [{id, ts, tx, wallet, token, side, usd, amount, symbol, ...}],
  tokens: [{token, symbol, liquidity, drained, ...}],
  metrics: {wallet_count, fill_count, token_count, closed_count,
            unpriced_fill_count, duplicate_fill_count, invalid_row_count,
            indexer_status, inferred_rule_count},
  warnings: [string, ...]
}
```

Wallet PnL, fills и win_rate сохраняют **значения upstream**, а не считаются по неполной ленте. Null остаётся null. Адреса canonical `(4663, lowercase address)`; payer/profile не становятся wallet. Fills сортируются `(ts,id)` и dedupe по source event id, **не tx**. Исходные дополнительные provenance-сигналы сохраняются. Closed records остаются в raw; `closed_count` — реально полученное число, а не запрошенный limit. Tokens сохраняют в том числе liquidity/drained/honeypot без украшений.

`wallet_rules` подключается, но его строгий execution boundary пока не получает Trenches rows: USD valuation не доказывает quote units, полная история/fees/pre-fill cash неизвестны. Выполняется пустой `analyze_fills(..., opening_inventory_known_zero=False)` и честно показывается insufficient_history, mapped_genes={}, inferred_rule_count=0. Это не ошибка: нельзя восстановить TP/SL, allocation или намерение по этим данным. При недоступности модуля явная метка no inference. Не выдаются score, neural confidence или fake wallet genome. Другой, более широкий валидированный адаптер может позднее заменить этот fail-closed boundary.

## Проверенный live результат

2026-09-14T20:06:30.134336Z: все пять endpoint **HTTP 200**; 147 wallets, 500 fills, **400 closed при запросе limit=500**, 100 tokens. Invalid rows 0, duplicates 0. Это не полная 7d история. Indexer chain_id=4663, source=websocket. Snapshot сохранён реальным CLI refresh.

Handle/address пары найдены в live roster (это проверка ответа индексатора, **не доказательство личности**):

- `unipcs` → `0x0a6ebed0155edb4b21d92ad02897a626cd90119e`
- `PoorGoat_` → `0x9ce0cb4a193acbce0dca3283972341aed6f3f614`
- `DumbCrayonEater` → `0x8f62a08537cede87d511aca6436274ab4ca080a3`
- `ether_monk` → `0x2408ce75d217e3a70d6ca370c78c1b34d706f5a0`

Реальный canonical fill, сокращённый до обязательных полей:

```json
{"id":99525,"ts":1789416379,"tx":"0x81cff80dbbd0695f14ad2f4db69752b9e9bc416b65b4040f4d6b44b4d6b8bc25","wallet":"0xbe1eaa605d3694639988dd4fcd7cee7ab8b1d74d","token":"0xbba60ab93fc409b1a34371cbf6c3173795ed2c7e","side":"buy","usd":442.317461,"amount":1699975.5536912715,"symbol":"PNL"}
```

Тесты проверяют сохранение null/PnL/id, tx с несколькими событиями, отсутствие выдуманных scores/rules, atomic snapshot roundtrip, stale fallback, пустой missing-cache и bounded retry/cache. Общий suite после интеграции: 24 tests OK. См. исходный аудит `data/reference-backend-audit.md` для границ индексатора и отдельной прежней RPC-проверки; этот ingestion сам RPC receipts не проверяет.
