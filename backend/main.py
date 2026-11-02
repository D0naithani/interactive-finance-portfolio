from io import StringIO
from typing import Literal, Optional
from pathlib import Path
from uuid import UUID
import pandas as pd
from fastapi import FastAPI, Query, Path as PathParam, HTTPException
from pydantic import BaseModel, Field, field_validator
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .analytics import read, reconcile, allocate, deal_summary, kpi_summary
from .reviews import store as reviews

app = FastAPI(title='Finance Workspace', version='2.0.0', description='Four independent portfolio demos. Synthetic data only.')
ROOT = Path(__file__).resolve().parent.parent


def csv_response(rows, name):
    return StreamingResponse(iter([pd.DataFrame(rows).to_csv(index=False)]), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="{name}.csv"'})


@app.get('/api/health')
def health():
    return {'status': 'ok', 'data': 'synthetic', 'version': '2.0.0'}


TRANSACTION_ID = PathParam(..., min_length=1, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')
SESSION_NOTE = 'Demo only: review state is in memory per visitor session, expires after 2 hours idle and resets on server restart.'


class Resolution(BaseModel):
    status: Literal['reviewed', 'resolved']
    note: str = Field('', max_length=280)

    @field_validator('note')
    @classmethod
    def clean_note(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('note must not contain control characters')
        return value.strip()


def csv_safe(value):
    # Visitor notes are exported: neutralise spreadsheet formula injection.
    return "'" + value if isinstance(value, str) and value[:1] in ('=', '+', '-', '@') else value


def find_row(transaction_id, tolerance_cents):
    row = next((r for r in reconcile(read('ledger'), read('bank'), tolerance_cents) if r['id'] == transaction_id), None)
    if row is None:
        raise HTTPException(404, 'Transaction not found')
    return row


@app.get('/api/quality')
def quality(q: str = Query('', max_length=100), status: Literal['all', 'matched', 'variance', 'missing_bank', 'missing_ledger', 'duplicate'] = 'all', tolerance_cents: int = Query(0, ge=0, le=10000), export: bool = False, session_id: Optional[UUID] = None):
    rows = reconcile(read('ledger'), read('bank'), tolerance_cents)
    rows = [r for r in rows if (status == 'all' or r['status'] == status) and (q.lower() in r['id'].lower() or q.lower() in r['account'].lower())]
    summary = {'records': len(rows), 'exceptions': sum(r['status'] != 'matched' for r in rows), 'absolute_variance_cents': sum(abs(r['variance_cents'] or 0) for r in rows)}
    if session_id is not None:
        decisions = reviews.get(str(session_id))
        for r in rows:
            # Matched rows are not exceptions at this tolerance; any stored decision is kept but not shown.
            d = decisions.get(r['id'], {}) if r['status'] != 'matched' else {}
            r.update(resolution_status=None if r['status'] == 'matched' else d.get('status', 'open'), resolution_note=d.get('note', ''), resolution_updated_at=d.get('updated_at'))
        summary['resolution'] = {k: sum(r['resolution_status'] == k for r in rows) for k in ('open', 'reviewed', 'resolved')}
    if export:
        return csv_response([{k: csv_safe(v) for k, v in r.items()} for r in rows], 'reconciliation')
    result = {'rows': rows, 'summary': summary, 'note': 'Variance excludes missing and duplicate records. Tolerance applies to absolute cent difference.'}
    if session_id is not None:
        result['session_note'] = SESSION_NOTE
    return result


@app.put('/api/quality/exceptions/{transaction_id}/resolution')
def resolve_exception(body: Resolution, transaction_id: str = TRANSACTION_ID, session_id: UUID = Query(...), tolerance_cents: int = Query(0, ge=0, le=10000)):
    row = find_row(transaction_id, tolerance_cents)
    if row['status'] == 'matched':
        raise HTTPException(409, 'Matched transactions are not exceptions and cannot be reviewed or resolved')
    try:
        record = reviews.set(str(session_id), transaction_id, body.status, body.note)
    except OverflowError as error:
        raise HTTPException(429, str(error))
    return {'id': transaction_id, 'status': row['status'], 'resolution_status': record['status'], 'resolution_note': record['note'], 'resolution_updated_at': record['updated_at'], 'session_note': SESSION_NOTE}


@app.delete('/api/quality/exceptions/{transaction_id}/resolution')
def reopen_exception(transaction_id: str = TRANSACTION_ID, session_id: UUID = Query(...)):
    find_row(transaction_id, 0)
    existed = reviews.reopen(str(session_id), transaction_id)
    return {'id': transaction_id, 'resolution_status': 'open', 'reopened': existed}


@app.delete('/api/quality/sessions/{session_id}')
def reset_session(session_id: UUID):
    return {'session_id': str(session_id), 'reset': reviews.reset(str(session_id))}


@app.get('/api/investors')
def investors(fund: Literal['All', 'Atlas I', 'Atlas II'] = 'All', distribution_cents: int = Query(10000000, ge=0, le=100000000000), export: bool = False):
    data = read('investors')
    if fund != 'All':
        data = data[data.fund == fund]
    rows = allocate(data, distribution_cents)
    if export:
        return csv_response(rows, 'investor-allocation')
    return {'rows': rows, 'summary': {'commitment_cents': int(data.commitment_cents.sum()), 'paid_in_cents': int(data.paid_in_cents.sum()), 'distribution_cents': sum(r['allocation_cents'] for r in rows)}, 'note': 'Illustrative pro-rata allocation by paid-in capital; All combines funds for demonstration. No fees, preferred returns or contractual waterfall.'}


@app.get('/api/deals')
def deals(stage: Literal['All', 'Sourcing', 'Screening', 'Diligence', 'Negotiation'] = 'All', export: bool = False):
    data = read('deals')
    if stage != 'All':
        data = data[data.stage == stage]
    rows = deal_summary(data)
    if export:
        return csv_response(rows, 'deal-pipeline')
    return {'rows': rows, 'summary': {'deals': len(rows), 'pipeline_cents': sum(r['enterprise_value_cents'] for r in rows), 'weighted_pipeline_cents': sum(r['weighted_value_cents'] for r in rows)}, 'note': 'Weighted pipeline = enterprise value × illustrative stage probability. This is a conceptual M&A product demo.'}


@app.get('/api/deals/{deal_id}')
def deal_detail(deal_id: str):
    data = read('deals')
    data = data[data.id == deal_id]
    if data.empty:
        raise HTTPException(404, 'Deal not found')
    return {'deal': deal_summary(data)[0], 'requirements': [
        {'feature': 'Financial screening', 'acceptance': 'Show revenue, EBITDA, valuation and source timestamp for each deal.'},
        {'feature': 'Diligence checklist', 'acceptance': 'Expose the next action, owner and blocker before stage handoff.'},
        {'feature': 'Decision review', 'acceptance': 'Capture reviewer sign-off and preserve an immutable audit record in a production implementation.'}],
        'workflow': ['Source opportunity', 'Screen financials', 'Review diligence', 'Negotiate terms', 'Decision review']}


@app.get('/api/kpis')
def kpis(channel: Literal['All', 'Organic', 'Paid', 'Partner'] = 'All', period: int = Query(6, ge=1, le=12), growth: float = Query(8, ge=0, le=100, allow_inf_nan=False), churn: float = Query(3, ge=0, le=100, allow_inf_nan=False), months: int = Query(6, ge=1, le=24), export: bool = False):
    data = read('kpis')
    if channel != 'All':
        data = data[data.channel == channel]
    data = data[data.month.isin(sorted(data.month.unique())[-period:])]
    result = kpi_summary(data, growth, churn, months)
    if export:
        return csv_response(result['rows'], 'founder-kpis')
    return {**result, 'note': 'Forecast compounds monthly: prior MRR × (1 + growth%) × (1 − churn%). Illustrative assumptions, not a validated forecast. CAC is marketing spend / new customers.'}


@app.get('/')
def index():
    return FileResponse(ROOT / 'frontend/index.html')


app.mount('/static', StaticFiles(directory=ROOT / 'frontend'), name='static')
