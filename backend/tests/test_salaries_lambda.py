import sys
from pathlib import Path
from decimal import Decimal
import json

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import salaries as lambda_mod
from utils.dynamodb import get_district_towns


class FakeTable:
    def __init__(self, items):
        self._items = items

    def query(self, **kwargs):
        return {'Items': self._items}


def test_compare_salaries_lambda(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'B',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('82000.25'),
        },
        {
            'district_id': 'd1',  # older period should be dropped
            'district_name': 'Alpha',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('80000.00'),
        },
        {
            'district_id': 'd2',
            'district_name': 'Beta',
            'district_type': 'regional',
            'school_year': '2022-2023',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': 75000,
        },
    ]

    monkeypatch.setattr(lambda_mod, 'salaries_table', FakeTable(items))
    monkeypatch.setattr('utils.dynamodb.get_district_towns', lambda ids, table_name: {'d1': ['Town1'], 'd2': ['Town2']})

    resp = lambda_mod.compare_salaries({'education': 'M', 'credits': '30', 'step': '5'})
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['total'] == 2
    assert body['results'][0]['district_id'] == 'd1'
    assert body['results'][0]['salary'] == 82000.25


def test_get_salary_heatmap_lambda(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'district_type': 'municipal',
            'school_year': '2021-2022',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('90000.5'),
        },
        {
            'district_id': 'd2',
            'district_name': 'Beta',
            'district_type': 'regional',
            'school_year': '2021-2022',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': 75000,
        },
    ]
    monkeypatch.setattr(lambda_mod, 'salaries_table', FakeTable(items))

    resp = lambda_mod.get_salary_heatmap({'education': 'M', 'credits': '30', 'step': '5', 'year': '2021-2022'})
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['statistics']['max'] == 90000.5
    assert len(body['data']) == 2


def test_get_salary_schedule_lambda(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'schedule_key': '2023-2024#A',
            'school_year': '2023-2024',
            'salaries': [{'step': 1, 'salary': Decimal('65000.0')}],
        }
    ]
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable(items))

    resp = lambda_mod.get_salary_schedule('d1')
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert isinstance(body, list) and body[0]['salaries'][0]['salary'] == 65000.0


def test_get_salary_metadata_lambda(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'school_year': '2022-2023',
            'period': 'A',
            'salaries': [{'step': 1, 'salary': Decimal('60000.0')}, {'step': 2, 'salary': 70000}],
            'contract_term': '2021-2024',
            'contract_expiration': '2024-08-31'
        },
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'school_year': '2023-2024',
            'period': 'B',
            'salaries': [{'step': 1, 'salary': 65000}, {'step': 2, 'salary': 80000}],
            'contract_term': '2021-2024',
            'contract_expiration': '2024-08-31'
        }
    ]
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable(items))

    resp = lambda_mod.get_salary_metadata('d1')
    assert resp['statusCode'] == 200
    meta = json.loads(resp['body'])
    assert meta['latest_year'] == '2023-2024'
    assert meta['salary_range']['min'] == 65000.0
    assert meta['salary_range']['max'] == 80000.0


def test_lambda_handler_routes(monkeypatch):
    # Patch functions used by handler
    monkeypatch.setattr(lambda_mod, 'get_salary_schedule', lambda did, year=None: lambda_mod.create_response(200, {'s': did, 'y': year}))
    monkeypatch.setattr(lambda_mod, 'compare_salaries', lambda params: lambda_mod.create_response(200, {'compare': True}))
    monkeypatch.setattr(lambda_mod, 'get_salary_heatmap', lambda params: lambda_mod.create_response(200, {'heatmap': True}))
    monkeypatch.setattr(lambda_mod, 'get_salary_metadata', lambda did: lambda_mod.create_response(200, {'meta': did}))

    # salary schedule with year
    e = {'path': '/api/salary-schedule/d1/2023-2024', 'httpMethod': 'GET'}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'s': 'd1', 'y': '2023-2024'}

    # salary compare
    e = {'path': '/api/salary-compare', 'httpMethod': 'GET', 'queryStringParameters': {'education': 'M', 'credits': '30', 'step': '5'}}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'compare': True}

    # salary heatmap
    e = {'path': '/api/salary-heatmap', 'httpMethod': 'GET', 'queryStringParameters': {'education': 'M', 'credits': '30', 'step': '5'}}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'heatmap': True}

    # salary metadata
    e = {'path': '/api/districts/d1/salary-metadata', 'httpMethod': 'GET'}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'meta': 'd1'}

    # not found
    e = {'path': '/nope', 'httpMethod': 'GET'}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 404
