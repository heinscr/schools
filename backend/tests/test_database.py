import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import types
import database


def test_init_db_skip_when_aws(monkeypatch):
    # No local endpoint => skip creation
    monkeypatch.setattr(database, 'DYNAMODB_ENDPOINT', None, raising=False)
    # Just ensure it returns without raising
    database.init_db()


def test_init_db_create_when_local(monkeypatch):
    # Simulate local endpoint and missing table
    monkeypatch.setattr(database, 'DYNAMODB_ENDPOINT', 'http://localhost:8000', raising=False)

    # Fake client with ResourceNotFoundException
    class RNF(Exception):
        pass
    fake_exceptions = types.SimpleNamespace(ResourceNotFoundException=RNF)

    class FakeClient:
        exceptions = fake_exceptions
        def describe_table(self, TableName):
            raise RNF('nope')

    # Fake resource that records create_table calls
    created = {}
    class FakeTable:
        def wait_until_exists(self):
            created['waited'] = True

    class FakeResource:
        def create_table(self, **kwargs):
            created['kwargs'] = kwargs
            return FakeTable()

    monkeypatch.setattr(database, 'dynamodb_client', FakeClient())
    monkeypatch.setattr(database, 'dynamodb_resource', FakeResource())

    database.init_db()

    assert 'kwargs' in created
    assert created['kwargs']['TableName'] == database.DISTRICTS_TABLE_NAME
    assert created.get('waited') is True


def test_get_table_returns_global(monkeypatch):
    # Ensure get_table returns the module's table object
    tbl = object()
    monkeypatch.setattr(database, 'districts_table', tbl)
    assert database.get_table() is tbl
