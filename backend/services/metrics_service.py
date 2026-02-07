from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging
import uuid

from database import get_table, dynamodb_client
from config import get_primary_timezone

logger = logging.getLogger(__name__)

ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _date_str_for_timestamp(ts: Optional[datetime]) -> str:
    tz = get_primary_timezone()
    if ts is None:
        dt = datetime.now(timezone.utc).astimezone(tz)
    else:
        # ensure timestamp is timezone-aware; assume UTC if naive
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        dt = ts.astimezone(tz)
    return dt.date().isoformat()


def track_event(table: Any, dynamodb_client: Any, event_time: Optional[datetime], user: Optional[Dict], anon_id: Optional[str], source: Optional[str] = None) -> Dict:
    """
    Track a single activity event by creating or updating a per-date/user item.

    Uses a DynamoDB item per (date, identifier) with PK="METRIC#DAU#<date>" and SK="USER#<id>" or "ANON#<id>".

    Updates `first_seen_at` if item is new and always updates `last_seen_at`.
    """
    now = datetime.now(timezone.utc)
    # normalize event_time to timezone-aware before computing date
    date_str = _date_str_for_timestamp(event_time or now)

    pk = f"METRIC#DAU#{date_str}"

    if user:
        user_id = user.get('sub')
        sk = f"USER#{user_id}"
        user_type = 'logged_in'
    else:
        if not anon_id:
            # Nothing to do without an identifier
            logger.debug('track_event: no anon_id and no user; dropping event')
            return {'ok': False, 'reason': 'missing_identifier'}
        user_id = None
        sk = f"ANON#{anon_id}"
        user_type = 'anonymous'

    # Use UpdateItem to create-or-update: set last_seen_at, and set first_seen_at if_not_exists
    try:
        table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression='SET #ut = :ut, #uid = :uid, #aid = :aid, #last = :last, #src = :src REMOVE #unused',
            ExpressionAttributeNames={
                '#ut': 'user_type',
                '#uid': 'user_id',
                '#aid': 'anon_id',
                '#last': 'last_seen_at',
                '#first': 'first_seen_at',
                '#src': 'source',
                '#unused': 'unused'
            },
            ExpressionAttributeValues={
                ':ut': user_type,
                ':uid': user_id if user_id else None,
                ':aid': anon_id if anon_id else None,
                ':last': now.isoformat().replace('+00:00', 'Z'),
                ':src': source if source else 'site'
            },
        )
    except Exception as e:
        # Some DynamoDB clients may reject None values; handle by building UpdateExpression without None fields
        # Fallback: build safe update expression
        attr_names = {'#ut': 'user_type', '#last': 'last_seen_at', '#first': 'first_seen_at', '#src': 'source'}
        expr_vals = {':ut': user_type, ':last': now.isoformat().replace('+00:00', 'Z'), ':src': source if source else 'site', ':first': now.isoformat().replace('+00:00', 'Z')}
        if user_id:
            attr_names['#uid'] = 'user_id'
            expr_vals[':uid'] = user_id
        if anon_id:
            attr_names['#aid'] = 'anon_id'
            expr_vals[':aid'] = anon_id

        update_parts = ["#ut = :ut", "#last = :last", "#src = :src", "#first = if_not_exists(first_seen_at, :first)"]
        if 'user_id' in attr_names:
            update_parts.insert(1, "#uid = :uid")
        if 'anon_id' in attr_names:
            update_parts.insert(1, "#aid = :aid")

        update_expr = 'SET ' + ', '.join(update_parts)

        table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=expr_vals,
        )

    return {'ok': True, 'date': date_str, 'pk': pk, 'sk': sk}


def merge_anon_to_user(table: Any, dynamodb_client: Any, date_str: str, anon_id: str, user_id: str) -> Dict:
    """
    Merge an anonymous identifier into a logged-in user for a single date.

    If an ANON item exists for (date_str, anon_id) and a USER item does not exist,
    create/update the USER item and delete the ANON item in a transaction to avoid double counting.
    If USER already exists, delete the ANON item.
    """
    pk = f"METRIC#DAU#{date_str}"
    anon_sk = f"ANON#{anon_id}"
    user_sk = f"USER#{user_id}"

    now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Check if user item exists
    try:
        resp = table.get_item(Key={'PK': pk, 'SK': user_sk})
        user_exists = 'Item' in resp
    except Exception:
        user_exists = False

    if user_exists:
        # If user exists, just attempt to delete anon item (idempotent)
        try:
            table.delete_item(Key={'PK': pk, 'SK': anon_sk})
        except Exception:
            logger.exception('Failed to delete anon item during merge')
        return {'ok': True, 'merged': False, 'reason': 'user_exists'}

    # Build transaction: Put user item (with first_seen_if_not_exists), Delete anon item
    transact_items = [
        {
            'Put': {
                'TableName': table.name,
                'Item': {
                    'PK': {'S': pk},
                    'SK': {'S': user_sk},
                    'user_type': {'S': 'logged_in'},
                    'user_id': {'S': user_id},
                    'last_seen_at': {'S': now_iso},
                    'first_seen_at': {'S': now_iso}
                },
                # Only put if user item does not already exist
                'ConditionExpression': 'attribute_not_exists(PK) AND attribute_not_exists(SK)'
            }
        },
        {
            'Delete': {
                'TableName': table.name,
                'Key': {
                    'PK': {'S': pk},
                    'SK': {'S': anon_sk}
                }
            }
        }
    ]

    try:
        dynamodb_client.transact_write_items(TransactItems=transact_items)
        return {'ok': True, 'merged': True}
    except Exception as e:
        logger.exception('transact_write_items failed during merge')
        # Fallback: try best-effort deletion of anon and creation of user
        try:
            table.update_item(
                Key={'PK': pk, 'SK': user_sk},
                UpdateExpression='SET user_type = :ut, user_id = :uid, last_seen_at = :last, first_seen_at = if_not_exists(first_seen_at, :first)',
                ExpressionAttributeValues={
                    ':ut': 'logged_in',
                    ':uid': user_id,
                    ':last': now_iso,
                    ':first': now_iso
                }
            )
            table.delete_item(Key={'PK': pk, 'SK': anon_sk})
            return {'ok': True, 'merged': True, 'fallback': True}
        except Exception:
            logger.exception('fallback merge failed')
            return {'ok': False, 'merged': False}


def count_dau_for_date(table: Any, date_str: str) -> Dict:
    """
    Return count breakdown for a given date. Returns total, logged_in_count, anonymous_count.
    """
    pk = f"METRIC#DAU#{date_str}"
    resp = table.query(KeyConditionExpression='PK = :pk', ExpressionAttributeValues={':pk': pk})
    items = resp.get('Items', [])
    total = len(items)
    logged = sum(1 for it in items if it.get('user_type') == 'logged_in')
    anon = total - logged
    return {'date': date_str, 'total': total, 'logged_in': logged, 'anonymous': anon}
