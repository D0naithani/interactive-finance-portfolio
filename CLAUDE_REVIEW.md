# Claude review: exception-resolution workflow (backend only)

Files touched: `backend/main.py` (edited), `backend/reviews.py` (new), `tests/test_resolution.py` (new). The frontend, docs, existing tests, dependencies and `backend/analytics.py` were not changed.

Tests: `../../work/venv/bin/python -m pytest -q` → **46 passed** (all existing tests plus the new resolution tests).

## Endpoint contract

`session_id` is always a **query parameter** holding a UUID (the client generates it, e.g. `crypto.randomUUID()`). A query parameter, not a header, so plain CSV download links work. Malformed UUIDs → 422.

| Method & path | Body | Result |
|---|---|---|
| `GET /api/quality?...&session_id=<uuid>` | – | Existing response, plus on every row: `resolution_status` (`open` / `reviewed` / `resolved`, `null` for matched rows), `resolution_note`, `resolution_updated_at` (ISO UTC or null). Adds `summary.resolution = {open, reviewed, resolved}` and `session_note`. Without `session_id` the response is byte-for-byte the old contract. |
| `GET /api/quality?export=true&session_id=<uuid>` | – | CSV with the same three extra columns. Notes starting with `= + - @` get a `'` prefix so spreadsheets don't run them as formulas. |
| `PUT /api/quality/exceptions/{transaction_id}/resolution?session_id=<uuid>[&tolerance_cents=N]` | `{"status": "reviewed"\|"resolved", "note": "≤280 chars, no control chars"}` | 200 `{id, status, resolution_status, resolution_note, resolution_updated_at, session_note}`. 404 if the ID isn't in the reconciliation; **409 if the row is `matched`** at the given tolerance (default 0); 422 if the ID fails `^[A-Za-z0-9_-]{1,32}$` or the body is invalid; 429 once a session holds 200 decisions. |
| `DELETE /api/quality/exceptions/{transaction_id}/resolution?session_id=<uuid>` | – | Reopen. 200 `{id, resolution_status: "open", reopened: bool}`, safe to repeat. 404 for an unknown ID. |
| `DELETE /api/quality/sessions/{session_id}` | – | Reset this visitor's decisions. 200 `{session_id, reset: bool}`. |

Financial fields (`ledger_cents`, `bank_cents`, `variance_cents`, `status`) and the existing `summary.exceptions` / `absolute_variance_cents` never change. The tests check this field by field.

## State model (demo only)

- `ReviewStore` in `backend/reviews.py`: a single `threading.Lock` around an LRU `OrderedDict`.
- A session expires after **2 h idle**. Reads refresh a session but never create one.
- At most **1000 sessions**; past that, the least recently used session is evicted. At most **200 decisions per session**.
- Everything is lost on restart. This is fine for the current single-worker `uvicorn` start command in `Dockerfile` / `render.yaml`. With `--workers > 1` or several instances, visitors would see inconsistent state.

## Remaining issues / notes for the frontend agent

- **Tolerance edge:** a decision saved for an exception stays stored if a higher tolerance later turns that row into `matched`. While matched, the row shows `resolution_status: null`. Lower the tolerance and the decision shows again. With the current data this can't happen: every variance is 12 500¢, above the 10 000¢ maximum tolerance.
- **No authentication.** Anyone holding a session UUID can read or change that session. This is acceptable for synthetic demo data only.
- **Reopen and tolerance:** reopen looks up the ID at tolerance 0, so it doesn't take a `tolerance_cents` parameter.

## `backend/analytics.py` review (reported only, not modified)

No errors that change the shipped synthetic numbers. Calculation risks:

1. **`reconcile`: float conversion after the outer merge.** NaN promotes the amount columns to float64, so `int(...)` loses precision above 2⁵³ cents (about $90T). This is negligible for this demo, but use nullable `Int64` dtypes if the code is reused.
2. **`reconcile`: duplicates hide context.** A duplicated ID is removed from *both* sides, including a valid single counterpart. It is then reported as one `duplicate` row with no account or amounts, so a reviewer can't see the amounts involved or how many copies exist.
3. **`reconcile`: IDs are not normalised.** Values like `"TX-0001 "` vs `"TX-0001"`, or different letter case, show up as two `missing_*` rows. Blank or non-numeric amounts (read with `keep_default_na=False`) raise an exception instead of becoming a data-quality row.
4. **`main.quality` summary (related):** `absolute_variance_cents` includes variances that fall within tolerance and are therefore `matched`. The label could suggest it covers only exceptions.
5. **`allocate`:** no check that individual `paid_in_cents` values are non-negative. A negative investor row would get a negative allocation while the total still adds up. `uncalled_cents` can be negative when an investor has paid in more than committed. Largest-remainder rounding and stable tie order are correct.
6. **`deal_summary`:** `int(Decimal)` truncates toward zero, so weighted values are biased down by less than 1¢ per deal. `probability` isn't checked to be in [0, 1], and a zero or negative revenue gives a `None` or negative multiple.
7. **`kpi_summary`:** the forecast compounds `(1+g)(1−c)` rather than `1+g−c`, and applies growth to the whole MRR base. Both are disclosed in the API note. `cac_cents` uses float `round` (half-even), while the forecast uses Decimal half-even, which is consistent. `customer_churn_pct` derives opening customers from closing − new + lost. This is correct given the data's continuity, which `test_mrr_continuity_and_customer_bridge` checks.
