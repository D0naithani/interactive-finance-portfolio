"""Regenerate all demo data deterministically. No network or real client data."""
import csv
from pathlib import Path
import random

OUT = Path(__file__).resolve().parent.parent / 'data'
OUT.mkdir(exist_ok=True)
rng = random.Random(42)


def save(name, rows):
    with (OUT / f'{name}.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


ledger = [dict(id=f'TX-{i:04}', account=['Operations', 'Revenue', 'Treasury'][i % 3], amount_cents=rng.randint(5000, 3000000)) for i in range(1, 61)]
bank = [dict(id=r['id'], amount_cents=r['amount_cents'] - (12500 if i % 11 == 0 else 0)) for i, r in enumerate(ledger) if i % 17 != 0]
bank.append(dict(id='TX-0099', amount_cents=85000))
ledger.append(ledger[5].copy())
save('ledger', ledger)
save('bank', bank)
save('investors', [dict(id=f'LP-{i:02}', investor=f'Synthetic Investor {i:02}', fund='Atlas I' if i <= 5 else 'Atlas II', commitment_cents=i * 10000000, paid_in_cents=i * 6500000, prior_distributions_cents=i * 850000) for i in range(1, 11)])
stages = [('Sourcing', .10), ('Screening', .25), ('Diligence', .55), ('Negotiation', .80)]
save('deals', [dict(id=f'D-{i:02}', company=f'{name} Labs', sector=['B2B SaaS', 'Fintech', 'Analytics'][i % 3], stage=stages[i % 4][0], probability=stages[i % 4][1], revenue_cents=(i + 2) * 100000000, enterprise_value_cents=(i + 2) * 450000000, ebitda_cents=(i + 2) * 18000000, owner=['Alex', 'Sam', 'Jordan'][i % 3], next_action=['Confirm data room access', 'Review revenue bridge', 'Schedule diligence review'][i % 3]) for i, name in enumerate(['Cedar', 'Ember', 'Northstar', 'Harbor', 'Orchid', 'Summit', 'Juniper', 'Quartz'], 1)])
rows = []
for c, channel in enumerate(['Organic', 'Paid', 'Partner']):
    mrr, customers = 900000 + c * 300000, 90 + c * 30
    for m in range(1, 13):
        new_customers = 10 + c * 3 + m
        lost_customers = 2 + c
        new_mrr, churned = new_customers * 10000, lost_customers * 10000
        customers += new_customers - lost_customers
        rows.append(dict(month=f'2026-{m:02}', channel=channel, opening_mrr_cents=mrr, new_mrr_cents=new_mrr, churned_mrr_cents=churned, customers=customers, new_customers=new_customers, lost_customers=lost_customers, marketing_cents=(new_customers * (12000 + c * 8000))))
        mrr += new_mrr - churned
save('kpis', rows)
