# DIVA / Interactive Systems Lab

Four interactive portfolio projects powered by a real Python FastAPI and pandas backend. The browser requests calculated results and CSV reports from the API; no analytics results are hardcoded in JavaScript.

**All organisations, investors, transactions and metrics are synthetic. These are independent portfolio demonstrations, not commissioned client deliverables.**

| Project | Demo route | Python work |
|---|---|---|
| Financial Data Quality Engine | `/#quality` | Outer-join reconciliation, duplicate quarantine, tolerance checks, missing records and variance summaries |
| Investor Operations Console | `/#investor` | Paid-in capital allocations, uncalled commitments and exact cent rounding |
| M&A SaaS Product Studio | `/#gro` | Stage filters, revenue multiples, probability-weighted deal values, detail and requirements APIs |
| Founder KPI Operating System | `/#kpi` | Monthly MRR bridge, channel aggregation, CAC, customer churn and compound scenario forecasts |

## Run locally

Use Python 3.11 (also tested locally with Python 3.9). From this repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
uvicorn backend.main:app --reload --port 8000
```

Open http://127.0.0.1:8000. Interactive API documentation: http://127.0.0.1:8000/docs. Health: `/api/health`.

No API keys, client files, database, frontend build or external fonts are required. This application serves its own frontend, so the UI and API share an origin. Opening `index.html` directly or serving it on GitHub Pages alone will not run Python.

## Calculation definitions

- **Reconciliation:** match unique transaction IDs across ledger and bank using an outer join. Quarantine any ID duplicated in either source before joining. Ledger − bank is the signed variance. A record matches when both sources exist and the absolute variance is within the configured cent tolerance. Missing records have null amounts/variance; they are never silently treated as zero. Absolute variance totals exclude missing and quarantined IDs.
- **Investor allocation:** scenario distribution × investor paid-in / selected paid-in total. Floor to whole cents, then assign residual cents to the largest fractional remainders, with stable source order for ties. Allocations sum to the requested distribution exactly. “All” deliberately combines the fictional funds. This is not a contractual waterfall and excludes fees, preferred returns, carry and tax.
- **M&A:** weighted pipeline = sum of enterprise value × stage probability. EV / revenue uses each deal's synthetic annual revenue. Probabilities are illustrative, not predicted outcomes. Requirements describe a conceptual production workflow; audit storage and diligence document processing are not implemented.
- **KPIs:** closing MRR = opening MRR + new MRR − churned MRR. ARR = latest closing MRR × 12. CAC = latest marketing spend / new customers. Customer churn = lost customers / opening customers; opening customers = closing − new + lost. Ratios use totals across selected channels, not averages of ratios. Forecast MRR compounds as prior MRR × (1 + growth / 100) × (1 − churn / 100), rounded to cents each month. Zero denominators return null. Scenario figures are illustrative, not validated forecasts.

Money is stored in integer USD cents. Decimal arithmetic is used for allocations and forecasting. Synthetic CSV amounts are small enough to preserve integer values through the outer join. API inputs are bounded and categorical filters are allowlisted. Financial source data is read-only; exception review decisions are stored separately for each visitor session. Do not repurpose it for confidential records without authentication, authorisation, data validation, storage and an audit trail.

Exception review uses Claude Code's `ReviewStore` implementation. The browser creates a UUID in session storage and sends it as `session_id`. Open a transaction to mark an exception reviewed/resolved, add a note or reopen it. Review decisions never change source amounts or the reconciliation status. Reset clears only the current visitor's decisions. State expires after two hours idle, is capped at 1,000 sessions / 200 decisions per session, and resets when the single server process restarts. Use one worker and one instance for this demo. These session IDs provide isolation for synthetic examples, not production authentication. See `CLAUDE_REVIEW.md` for the endpoint contract and limitations.

## API examples

```sh
curl 'http://127.0.0.1:8000/api/quality?status=variance&tolerance_cents=0'
curl 'http://127.0.0.1:8000/api/investors?fund=Atlas%20I&distribution_cents=10000001'
curl 'http://127.0.0.1:8000/api/deals?stage=Diligence'
curl 'http://127.0.0.1:8000/api/deals/D-01'
curl 'http://127.0.0.1:8000/api/kpis?channel=Paid&period=6&growth=10&churn=3'
curl 'http://127.0.0.1:8000/api/quality?export=true' -o reconciliation.csv
```

All four collection endpoints support `export=true` and preserve the selected filters. Full parameter schemas and bounds are in `/docs`.

## Synthetic data and tests

Committed CSV fixtures live in `data/`. Run `python scripts/generate_data.py` to regenerate them with seed 42. This overwrites only the five synthetic source CSVs. No internet access is used. Tests cover known numeric results, exact allocation conservation, duplicates, missing records, zero denominators, forecast boundaries, MRR continuity, API filters, invalid input, CSV parity and static delivery. GitHub Actions runs the tests on pushes and pull requests.

## Publish source on GitHub

Create a public repository called `interactive-finance-portfolio` and upload this folder's **contents**, including `backend/`, `frontend/`, `data/`, `tests/`, `scripts/` and `.github/`. Do not upload a virtual environment, `.env` or caches. Alternatively:

```sh
git init -b main
git add .
git commit -m "Build four FastAPI portfolio demonstrations"
git remote add origin https://github.com/YOUR_USERNAME/interactive-finance-portfolio.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual account. These commands are instructions; they do not mean publication has occurred. GitHub Pages hosts static files and does not execute this FastAPI backend.

## Deploy the live demos on Render

The repository includes `render.yaml`. In Render, create a new Blueprint from the published GitHub repository, review the free service selection and deploy. Or create a Python web service manually:

| Setting | Value |
|---|---|
| Build | `pip install -r requirements.txt` |
| Start | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/api/health` |
| Python | 3.11 |

The service serves both UI and API. Free service availability and limits depend on the hosting account; idle services may need time to start. Follow [Render's FastAPI guide](https://render.com/docs/deploy-fastapi). No paid hosting is authorised by these setup instructions.

Alternative: `docker build -t diva-portfolio .` then `docker run --rm -p 8000:8000 diva-portfolio`. Any container host supporting HTTP and its `PORT` environment variable can run this image.

## Verify publication before sharing

1. Open the actual public repository and inspect `backend/main.py`, `frontend/app.js` and the tests.
2. Confirm GitHub Actions is green.
3. Open the actual hosting URL and `/api/health`; verify `status=ok` and `data=synthetic`.
4. Open each `/#quality`, `/#investor`, `/#gro`, `/#kpi` link. Change a filter or scenario and verify the visible results change. Download a CSV.
5. Add the actual verified links to Upwork; never use placeholder URLs or label a local preview “live”.

See `portfolio/UPWORK.md` for the four project descriptions and screenshots. `PUBLICATION_STATUS.md` records observed publishing state separately from code readiness.

## Architecture

```text
Vanilla JavaScript UI → same-origin FastAPI routes → pandas / Decimal analytics
                                                       ↓
                                          deterministic synthetic CSVs
```

Framework references: [FastAPI static files](https://fastapi.tiangolo.com/tutorial/static-files/), [pandas merge](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.merge.html).
