import sys
from pathlib import Path
import json

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import salaries as lambda_mod
from utils.dynamodb import get_district_towns


def test_compare_salaries_missing_params(monkeypatch):
    """Test that missing parameters raise ValueError"""
    monkeypatch.setattr(lambda_mod, 'salaries_table', object())
    import pytest
    with pytest.raises(ValueError, match="Step parameter is required"):
        lambda_mod.compare_salaries({'education': 'M', 'credits': '30'})  # missing step


def test_heatmap_missing_params(monkeypatch):
    """Test that missing parameters raise ValueError"""
    monkeypatch.setattr(lambda_mod, 'salaries_table', object())
    import pytest
    with pytest.raises(ValueError, match="Credits parameter is required"):
        lambda_mod.get_salary_heatmap({'education': 'M', 'step': '5'})  # missing credits


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


def test_get_district_towns_empty_inputs():
    # Test empty inputs return empty dict
    assert get_district_towns([], '') == {}


def test_get_district_towns_exception(monkeypatch):
    # Force batch_get_item to raise to cover exception path
    import boto3

    class FakeClient:
        def batch_get_item(self, **_kwargs):
            raise RuntimeError('boom')

    monkeypatch.setattr(boto3, 'client', lambda *args, **kwargs: FakeClient())
    out = get_district_towns(['d1', 'd2'], 'test_table')
    assert out == {}
