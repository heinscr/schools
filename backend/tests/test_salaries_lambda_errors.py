import sys
from pathlib import Path
import json

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import salaries as lambda_mod


def test_compare_salaries_missing_params(monkeypatch):
    monkeypatch.setattr(lambda_mod, 'salaries_table', object())
    resp = lambda_mod.compare_salaries({'education': 'M', 'credits': '30'})  # missing step
    assert resp['statusCode'] == 400


def test_heatmap_missing_params(monkeypatch):
    monkeypatch.setattr(lambda_mod, 'salaries_table', object())
    resp = lambda_mod.get_salary_heatmap({'education': 'M', 'step': '5'})  # missing credits
    assert resp['statusCode'] == 400


def test_schedule_not_configured(monkeypatch):
    monkeypatch.setattr(lambda_mod, 'schedules_table', None)
    resp = lambda_mod.get_salary_schedule('d1')
    assert resp['statusCode'] == 503


def test_metadata_not_configured(monkeypatch):
    monkeypatch.setattr(lambda_mod, 'schedules_table', None)
    resp = lambda_mod.get_salary_metadata('d1')
    assert resp['statusCode'] == 503


def test_schedule_not_found(monkeypatch):
    class FakeTable:
        def query(self, **kwargs):
            return {'Items': []}
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable())
    resp = lambda_mod.get_salary_schedule('d1')
    assert resp['statusCode'] == 404


def test_metadata_not_found(monkeypatch):
    class FakeTable:
        def query(self, **kwargs):
            return {'Items': []}
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable())
    resp = lambda_mod.get_salary_metadata('d1')
    assert resp['statusCode'] == 404


def test_get_district_towns_empty_inputs(monkeypatch):
    monkeypatch.setattr(lambda_mod, 'districts_table', None)
    assert lambda_mod.get_district_towns([]) == {}


def test_get_district_towns_exception(monkeypatch):
    # Force batch_get_item to raise to cover exception path
    class FakeClient:
        def batch_get_item(self, **kwargs):
            raise RuntimeError('boom')
    monkeypatch.setattr(lambda_mod, 'districts_table', object())
    monkeypatch.setattr(lambda_mod, 'DISTRICTS_TABLE_NAME', 'tbl')
    monkeypatch.setattr(lambda_mod.boto3, 'client', lambda *_args, **_kw: FakeClient())
    out = lambda_mod.get_district_towns(['d1', 'd2'])
    assert out == {}
