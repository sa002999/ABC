from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


TOKYO=ZoneInfo('Asia/Tokyo')


def utcnow(): return datetime.now(timezone.utc)


def in_window(starts_at,now=None):
    delta=starts_at-(now or utcnow())
    return timedelta(hours=24)<=delta<=timedelta(days=90)


def effective_hold(row):
    return 'EXPIRED' if row['status']=='HELD' and row['expires_at']<=utcnow() else row['status']
