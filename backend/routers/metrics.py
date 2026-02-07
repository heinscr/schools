from fastapi import APIRouter, Depends, Request, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta

from database import get_table, dynamodb_client
from cognito_auth import get_current_user_optional, require_admin_role
from services.metrics_service import track_event, merge_anon_to_user, count_dau_for_date
from config import get_primary_timezone

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.post('/track')
async def track(request: Request, user: dict = Depends(get_current_user_optional), table = Depends(get_table)):
    """Ingest a tracking event. Accepts JSON: { anon_id?: string, event?: string, timestamp?: ISO8601 }
    Authentication optional - if provided, event will be associated with logged-in user.
    """
    payload = await request.json()
    anon_id = payload.get('anon_id')
    event = payload.get('event', 'page_view')
    ts = payload.get('timestamp')
    source = payload.get('source')

    event_time = None
    if ts:
        try:
            event_time = datetime.fromisoformat(ts)
        except Exception:
            event_time = None

    result = track_event(table=table, dynamodb_client=dynamodb_client, event_time=event_time, user=user, anon_id=anon_id, source=source)

    # If anon_id present and user present, attempt merge for the date
    if anon_id and user:
        date_str = (event_time or datetime.utcnow()).astimezone(get_primary_timezone()).date().isoformat()
        try:
            merge_anon_to_user(table=table, dynamodb_client=dynamodb_client, date_str=date_str, anon_id=anon_id, user_id=user.get('sub'))
        except Exception:
            pass

    return { 'ok': True, 'result': result }


@router.get('/admin/dau')
async def get_dau(start: Optional[str] = Query(None), end: Optional[str] = Query(None), user: dict = Depends(require_admin_role), table = Depends(get_table)):
    """Admin endpoint: return DAU counts for dates in range (inclusive)."""
    tz = get_primary_timezone()

    def _parse_or_default(s, default):
        if s:
            try:
                return datetime.fromisoformat(s).date()
            except Exception:
                raise HTTPException(status_code=400, detail='invalid date')
        return default

    today = datetime.now(tz).date()
    start_date = _parse_or_default(start, today - timedelta(days=29))
    end_date = _parse_or_default(end, today)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail='start must be before end')

    results = []
    cur = start_date
    while cur <= end_date:
        ds = cur.isoformat()
        try:
            cnt = count_dau_for_date(table=table, date_str=ds)
            results.append(cnt)
        except Exception:
            results.append({'date': ds, 'total': 0, 'logged_in': 0, 'anonymous': 0})
        cur = cur + timedelta(days=1)

    return {'data': results}
