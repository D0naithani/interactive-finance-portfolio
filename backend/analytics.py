"""Deterministic, synthetic portfolio analytics. Money is stored as integer cents."""
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / 'data'


def read(name):
    return pd.read_csv(DATA / f'{name}.csv', keep_default_na=False)


def reconcile(ledger, bank, tolerance_cents=0):
    # Duplicate identifiers are quarantined before joining: never multiply money.
    duplicates = set(ledger.loc[ledger.id.duplicated(False), 'id']) | set(bank.loc[bank.id.duplicated(False), 'id'])
    rows = ledger[~ledger.id.isin(duplicates)].merge(
        bank[~bank.id.isin(duplicates)], on='id', how='outer',
        suffixes=('_ledger', '_bank'), indicator=True, validate='one_to_one')
    result = []
    for r in rows.to_dict('records'):
        left = None if pd.isna(r.get('amount_cents_ledger')) else int(r['amount_cents_ledger'])
        right = None if pd.isna(r.get('amount_cents_bank')) else int(r['amount_cents_bank'])
        variance = None if left is None or right is None else left - right
        status = 'missing_ledger' if left is None else 'missing_bank' if right is None else 'matched' if abs(variance) <= tolerance_cents else 'variance'
        result.append(dict(id=r['id'], account=r.get('account', '') if isinstance(r.get('account'), str) else '', ledger_cents=left, bank_cents=right, variance_cents=variance, status=status))
    for key in sorted(duplicates):
        result.append(dict(id=key, account='', ledger_cents=None, bank_cents=None, variance_cents=None, status='duplicate'))
    return result


def allocate(investors, amount_cents):
    total = int(investors.paid_in_cents.sum())
    if total <= 0:
        raise ValueError('No paid-in capital for this fund')
    raw = [Decimal(amount_cents) * Decimal(int(n)) / Decimal(total) for n in investors.paid_in_cents]
    cents = [int(n.to_integral_value(rounding=ROUND_FLOOR)) for n in raw]
    remainder = amount_cents - sum(cents)
    # Largest remainder, stable source order for ties; allocations sum exactly.
    order = sorted(range(len(raw)), key=lambda i: raw[i] - cents[i], reverse=True)
    for i in order[:remainder]:
        cents[i] += 1
    rows = investors.to_dict('records')
    for i, row in enumerate(rows):
        row.update(allocation_cents=cents[i], share=float(Decimal(int(row['paid_in_cents'])) / Decimal(total)), uncalled_cents=int(row['commitment_cents']) - int(row['paid_in_cents']))
    return rows


def deal_summary(frame):
    rows = frame.to_dict('records')
    for r in rows:
        r['weighted_value_cents'] = int(Decimal(int(r['enterprise_value_cents'])) * Decimal(str(r['probability'])))
        r['ev_revenue_multiple'] = round(r['enterprise_value_cents'] / r['revenue_cents'], 2) if r['revenue_cents'] else None
    return rows


def kpi_summary(frame, growth, churn, months):
    # Monthly bridge is explicit: opening + new - churned = closing MRR.
    if frame.empty:
        return dict(rows=[], summary={}, forecast=[])
    monthly = frame.groupby('month', as_index=False).agg({c: 'sum' for c in ['opening_mrr_cents', 'new_mrr_cents', 'churned_mrr_cents', 'customers', 'new_customers', 'lost_customers', 'marketing_cents']})
    monthly['closing_mrr_cents'] = monthly.opening_mrr_cents + monthly.new_mrr_cents - monthly.churned_mrr_cents
    latest = monthly.iloc[-1]
    opening_customers = int(latest.customers - latest.new_customers + latest.lost_customers)
    summary = dict(mrr_cents=int(latest.closing_mrr_cents), arr_cents=int(latest.closing_mrr_cents) * 12,
                   customers=int(latest.customers), cac_cents=round(int(latest.marketing_cents) / int(latest.new_customers)) if latest.new_customers else None,
                   customer_churn_pct=round(int(latest.lost_customers) / opening_customers * 100, 2) if opening_customers else None)
    forecast, value = [], int(latest.closing_mrr_cents)
    for step in range(1, months + 1):
        value = int((Decimal(value) * (Decimal(1) + Decimal(str(growth)) / 100) * (Decimal(1) - Decimal(str(churn)) / 100)).quantize(Decimal('1')))
        forecast.append(dict(month=step, mrr_cents=value))
    return dict(rows=monthly.to_dict('records'), summary=summary, forecast=forecast)
