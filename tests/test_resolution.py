import io
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.reviews import ReviewStore, store

client = TestClient(app)
FINANCIAL = ('id', 'account', 'ledger_cents', 'bank_cents', 'variance_cents', 'status')


@pytest.fixture
def session():
    sid = str(uuid4())
    yield sid
    store.reset(sid)


def rows_by_id(sid=None, **params):
    if sid:
        params['session_id'] = sid
    return {r['id']: r for r in client.get('/api/quality', params=params).json()['rows']}


def resolve(sid, tx, status='resolved', note='', **params):
    return client.put(f'/api/quality/exceptions/{tx}/resolution', params={'session_id': sid, **params}, json={'status': status, 'note': note})


def test_resolution_lifecycle_never_changes_financial_fields(session):
    before = rows_by_id()
    assert resolve(session, 'TX-0012', 'reviewed', ' checking FX ').json()['resolution_status'] == 'reviewed'
    assert resolve(session, 'TX-0001', 'resolved').status_code == 200
    after = rows_by_id(session)
    assert after['TX-0012']['resolution_status'] == 'reviewed'
    assert after['TX-0012']['resolution_note'] == 'checking FX'
    assert after['TX-0001']['resolution_status'] == 'resolved'
    assert after['TX-0018']['resolution_status'] == 'open'
    assert after['TX-0002']['resolution_status'] is None  # matched rows are not exceptions
    for tx, row in before.items():
        assert {k: after[tx][k] for k in FINANCIAL} == row
    summary = client.get('/api/quality', params={'session_id': session}).json()['summary']
    assert summary['exceptions'] == sum(r['status'] != 'matched' for r in before.values())
    assert summary['resolution'] == {'open': summary['exceptions'] - 2, 'reviewed': 1, 'resolved': 1}

    reopened = client.delete('/api/quality/exceptions/TX-0012/resolution', params={'session_id': session}).json()
    assert reopened == {'id': 'TX-0012', 'resolution_status': 'open', 'reopened': True}
    assert client.delete('/api/quality/exceptions/TX-0012/resolution', params={'session_id': session}).json()['reopened'] is False
    assert rows_by_id(session)['TX-0012']['resolution_status'] == 'open'


def test_all_exception_kinds_resolvable_matched_rejected(session):
    for tx in ('TX-0012', 'TX-0001', 'TX-0099', 'TX-0006'):  # variance, missing_bank, missing_ledger, duplicate
        assert resolve(session, tx).status_code == 200
    response = resolve(session, 'TX-0002')
    assert response.status_code == 409
    assert rows_by_id(session)['TX-0002']['resolution_status'] is None


def test_sessions_are_isolated_and_reset(session):
    other = str(uuid4())
    resolve(session, 'TX-0012')
    assert rows_by_id(other)['TX-0012']['resolution_status'] == 'open'
    assert 'resolution_status' not in rows_by_id()['TX-0012']  # no session: original contract
    assert client.delete(f'/api/quality/sessions/{session}').json() == {'session_id': session, 'reset': True}
    assert rows_by_id(session)['TX-0012']['resolution_status'] == 'open'
    assert client.delete(f'/api/quality/sessions/{session}').json()['reset'] is False


def test_csv_includes_resolution_and_neutralises_formulas(session):
    resolve(session, 'TX-0012', note='=HYPERLINK("http://x")')
    csv = client.get('/api/quality', params={'session_id': session, 'export': 'true'})
    frame = pd.read_csv(io.StringIO(csv.text), keep_default_na=False).set_index('id')
    assert {'resolution_status', 'resolution_note', 'resolution_updated_at'} <= set(frame.columns)
    assert frame.loc['TX-0012', 'resolution_status'] == 'resolved'
    assert frame.loc['TX-0012', 'resolution_note'].startswith("'=")
    assert frame.loc['TX-0001', 'resolution_status'] == 'open'
    plain = pd.read_csv(io.StringIO(client.get('/api/quality?export=true').text))
    assert 'resolution_status' not in plain.columns


def test_filters_still_apply_with_session(session):
    resolve(session, 'TX-0012')
    rows = rows_by_id(session, status='variance')
    assert set(r['status'] for r in rows.values()) == {'variance'}
    assert rows['TX-0012']['resolution_status'] == 'resolved'


@pytest.mark.parametrize('method, path, params, body', [
    ('put', '/api/quality/exceptions/TX-0012/resolution', {'session_id': 'not-a-uuid'}, {'status': 'resolved'}),
    ('put', '/api/quality/exceptions/TX-0012/resolution', {}, {'status': 'resolved'}),
    ('put', '/api/quality/exceptions/TX-0012/resolution', None, {'status': 'matched'}),
    ('put', '/api/quality/exceptions/TX-0012/resolution', None, {'status': 'resolved', 'note': 'x' * 281}),
    ('put', '/api/quality/exceptions/TX-0012/resolution', None, {'status': 'resolved', 'note': 'a\nb'}),
    ('put', '/api/quality/exceptions/TX-0012/resolution', {'tolerance_cents': -1}, {'status': 'resolved'}),
    ('put', '/api/quality/exceptions/TX%200012/resolution', None, {'status': 'resolved'}),
    ('put', '/api/quality/exceptions/' + 'A' * 33 + '/resolution', None, {'status': 'resolved'}),
    ('delete', '/api/quality/exceptions/TX-0012/resolution', {'session_id': 'nope'}, None),
    ('delete', '/api/quality/sessions/not-a-uuid', {}, None),
    ('get', '/api/quality', {'session_id': 'nope'}, None),
])
def test_invalid_inputs_rejected(method, path, params, body):
    params = {'session_id': str(uuid4())} if params is None else params
    assert client.request(method.upper(), path, params=params, json=body).status_code == 422


def test_unknown_transaction_is_404(session):
    assert resolve(session, 'TX-9999').status_code == 404
    assert client.delete('/api/quality/exceptions/TX-9999/resolution', params={'session_id': session}).status_code == 404


def test_store_expires_and_evicts():
    now = [0.0]
    s = ReviewStore(ttl_seconds=10, max_sessions=2, max_reviews=2, clock=lambda: now[0])
    s.set('a', 'TX-1', 'reviewed')
    now[0] = 5
    s.set('b', 'TX-1', 'resolved')
    now[0] = 9
    assert s.get('a')  # reading refreshes 'a'
    now[0] = 16
    assert s.get('b') == {}  # 'b' idle 11s: expired
    assert s.get('a')
    s.set('c', 'TX-1', 'reviewed')
    s.set('d', 'TX-1', 'reviewed')  # over capacity: least recently used ('a') evicted
    assert s.get('a') == {} and len(s) == 2
    s.set('c', 'TX-2', 'reviewed')
    s.set('c', 'TX-2', 'resolved')  # updating an existing decision does not count against the cap
    with pytest.raises(OverflowError):
        s.set('c', 'TX-3', 'reviewed')
    with pytest.raises(ValueError):
        s.set('c', 'TX-1', 'open')
    assert s.get('nobody') == {} and len(s) == 2  # reads never create sessions


def test_store_returns_copies():
    s = ReviewStore()
    s.set('a', 'TX-1', 'reviewed')
    s.get('a')['TX-1']['status'] = 'tampered'
    assert s.get('a')['TX-1']['status'] == 'reviewed'


def test_store_thread_safety():
    s = ReviewStore(max_sessions=50, max_reviews=100)

    def work(i):
        sid = f's{i % 60}'
        s.set(sid, f'TX-{i % 100}', 'reviewed')
        s.get(sid)
        if i % 7 == 0:
            s.reopen(sid, f'TX-{i % 100}')
        if i % 13 == 0:
            s.reset(sid)

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(work, range(3000)))
    assert len(s) <= 50
