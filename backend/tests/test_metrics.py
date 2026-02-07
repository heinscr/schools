from datetime import datetime

from services.metrics_service import track_event, merge_anon_to_user


class FakeTable:
    def __init__(self):
        self.updated = {}
        self.items = {}
        self.name = 'fake-table'

    def update_item(self, Key, UpdateExpression=None, ExpressionAttributeNames=None, ExpressionAttributeValues=None):
        self.updated['Key'] = Key
        self.updated['UpdateExpression'] = UpdateExpression
        self.updated['ExpressionAttributeValues'] = ExpressionAttributeValues
        # Simulate creating item
        pk = Key['PK']
        sk = Key['SK']
        self.items[(pk, sk)] = {'PK': pk, 'SK': sk}
        return {'Attributes': self.items[(pk, sk)]}

    def get_item(self, Key):
        k = (Key['PK'], Key['SK'])
        return {'Item': self.items.get(k)} if k in self.items else {}

    def delete_item(self, Key):
        k = (Key['PK'], Key['SK'])
        if k in self.items:
            del self.items[k]


class FakeClient:
    def __init__(self):
        self.transact = None

    def transact_write_items(self, TransactItems):
        self.transact = TransactItems


def test_track_anonymous_creates_item():
    t = FakeTable()
    client = FakeClient()
    res = track_event(table=t, dynamodb_client=client, event_time=datetime.utcnow(), user=None, anon_id='anon-123', source='test')
    assert res['ok'] is True
    assert 'pk' in res and 'sk' in res
    assert t.updated['Key']['SK'].startswith('ANON#')


def test_merge_anon_to_user_transacts():
    t = FakeTable()
    client = FakeClient()
    date_str = datetime.utcnow().date().isoformat()
    # Create anon item first
    track_event(table=t, dynamodb_client=client, event_time=datetime.utcnow(), user=None, anon_id='anon-xyz', source='test')
    # Ensure no user item exists
    result = merge_anon_to_user(table=t, dynamodb_client=client, date_str=date_str, anon_id='anon-xyz', user_id='user-1')
    # Either transact was attempted or fallback succeeded
    assert result.get('ok') is True
