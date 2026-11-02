from decimal import Decimal
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.analytics import reconcile, allocate, kpi_summary

client = TestClient(app)


def test_reconciliation_outer_join_and_duplicates():
    ledger = pd.DataFrame({'id': ['a', 'b', 'c', 'd', 'd'], 'amount_cents': [100, 200, 300, 40, 40]})
    bank = pd.DataFrame({'id': ['a', 'b', 'e', 'd'], 'amount_cents': [100, 190, 20, 40]})
    rows = {r['id']: r for r in reconcile(ledger, bank)}
    assert {k: r['status'] for k, r in rows.items()} == {'a': 'matched', 'b': 'variance', 'c': 'missing_bank', 'e': 'missing_ledger', 'd': 'duplicate'}
    assert rows['b']['variance_cents'] == 10
    assert rows['c']['bank_cents'] is None
    assert {r['id']: r for r in reconcile(ledger, bank, 10)}['b']['status'] == 'matched'


@pytest.mark.parametrize('amount', [0, 1, 2, 100, 10000001, 100000000000])
def test_allocation_conserves_cents(amount):
    investors = pd.DataFrame({'paid_in_cents': [1, 1, 1], 'commitment_cents': [2, 2, 2]})
    rows = allocate(investors, amount)
    assert sum(r['allocation_cents'] for r in rows) == amount
    assert max(r['allocation_cents'] for r in rows) - min(r['allocation_cents'] for r in rows) <= 1
    if amount == 1:
        assert rows[0]['allocation_cents'] == 1


def test_kpi_known_calculation():
    data = pd.DataFrame([dict(month='2026-01', opening_mrr_cents=10000, new_mrr_cents=3000, churned_mrr_cents=1000, customers=12, new_customers=3, lost_customers=1, marketing_cents=9000)])
    result = kpi_summary(data, growth=10, churn=5, months=1)
    assert result['summary'] == dict(mrr_cents=12000, arr_cents=144000, customers=12, cac_cents=3000, customer_churn_pct=10.0)
    assert result['forecast'] == [dict(month=1, mrr_cents=12540)]
    assert kpi_summary(data, 0, 100, 2)['forecast'][-1]['mrr_cents'] == 0
    assert kpi_summary(data.iloc[:0], 0, 0, 1)['rows'] == []


@pytest.mark.parametrize('path', ['/api/quality', '/api/investors', '/api/deals', '/api/kpis'])
def test_api_and_csv_contract(path):
    result = client.get(path)
    assert result.status_code == 200
    assert result.json()['rows']
    csv = client.get(path + '?export=true')
    assert csv.status_code == 200
    assert csv.headers['content-type'].startswith('text/csv')
    assert len(pd.read_csv(__import__('io').StringIO(csv.text))) == len(result.json()['rows'])


@pytest.mark.parametrize('path', ['/api/quality?status=bad', '/api/quality?tolerance_cents=-1', '/api/investors?distribution_cents=-1', '/api/investors?fund=Other', '/api/kpis?growth=nan', '/api/kpis?growth=inf', '/api/kpis?churn=101', '/api/kpis?period=0', '/api/kpis?months=25', '/api/deals?stage=Unknown'])
def test_invalid_inputs_rejected(path):
    assert client.get(path).status_code == 422


def test_filtering_and_no_match():
    assert client.get('/api/quality?q=DOESNOTEXIST').json()['rows'] == []
    assert all(r['status'] == 'variance' for r in client.get('/api/quality?status=variance').json()['rows'])
    assert len(client.get('/api/investors?fund=Atlas%20I').json()['rows']) == 5
    assert all(r['stage'] == 'Diligence' for r in client.get('/api/deals?stage=Diligence').json()['rows'])
    assert len(client.get('/api/kpis?period=3').json()['rows']) == 3
    assert client.get('/api/kpis?channel=Paid').json()['summary']['mrr_cents'] < client.get('/api/kpis').json()['summary']['mrr_cents']


def test_deal_detail_and_weighted_values():
    data = client.get('/api/deals').json()
    assert data['summary']['weighted_pipeline_cents'] == sum(r['weighted_value_cents'] for r in data['rows'])
    for r in data['rows']:
        assert r['weighted_value_cents'] == int(Decimal(r['enterprise_value_cents']) * Decimal(str(r['probability'])))
    assert client.get('/api/deals/D-01').json()['requirements']
    assert client.get('/api/deals/does-not-exist').status_code == 404


def test_mrr_continuity_and_customer_bridge():
    from backend.analytics import read
    data = read('kpis')
    for _, group in data.groupby('channel'):
        rows = group.to_dict('records')
        for previous, current in zip(rows, rows[1:]):
            assert current['opening_mrr_cents'] == previous['opening_mrr_cents'] + previous['new_mrr_cents'] - previous['churned_mrr_cents']
            assert current['customers'] == previous['customers'] + current['new_customers'] - current['lost_customers']


def test_static_and_health():
    assert client.get('/api/health').json()['status'] == 'ok'
    assert 'Finance Workspace' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/openapi.json').status_code == 200
