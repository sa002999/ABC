"""Explicit demo fixtures. Reruns never overwrite inventory state or slot capacity."""
from datetime import datetime, time, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from database import connect
from seed_catalog import CATALOG, identifier

NAMESPACE=UUID('5281aa4b-3ca8-40f9-b231-3a1362f97aa2')


def seed_booking():
    tokyo=ZoneInfo('Asia/Tokyo')
    today=datetime.now(tokyo).date()
    with connect() as connection:
        stores=connection.execute("SELECT id,slug FROM stores WHERE active AND is_demo AND slug IN ('demo-kyoto','demo-tokyo')").fetchall()
        if len(stores)!=2: raise RuntimeError('Run seed-demo and seed-catalog first.')
        for store in stores:
            connection.execute("INSERT INTO store_booking_settings(store_id,cleaning_minutes,closes_at,is_demo) VALUES (%s,120,'19:00',true) ON CONFLICT DO NOTHING",(store['id'],))
            for day in range(1,91):
                for hour in (9,10):
                    start=datetime.combine(today+timedelta(days=day),time(hour),tokyo)
                    slot_id=uuid5(NAMESPACE,'demo-slot:'+store['slug']+':'+start.isoformat())
                    connection.execute('''INSERT INTO availability_slots(id,store_id,starts_at,ends_at,capacity_total,is_demo)
                        VALUES (%s,%s,%s,%s,3,true) ON CONFLICT DO NOTHING''',(slot_id,store['id'],start,start+timedelta(minutes=30)))
        by_slug={row['slug']:row['id'] for row in stores}
        for sku,_,_,_,_,slug,_ in CATALOG:
            for number in (1,2,3):
                code=f'DEMO-{sku}-{number:03d}'
                connection.execute('''INSERT INTO inventory_items(id,code,store_id,kimono_id,is_demo)
                    VALUES (%s,%s,%s,%s,true) ON CONFLICT DO NOTHING''',
                    (uuid5(NAMESPACE,'inventory:'+code),code,by_slug[slug],identifier('kimono',sku)))
    print('Demo booking data ready: 09:00/10:00 Tokyo-time slots, capacity 3, 9 physical items, 120-minute cleaning. Existing rows preserved.')
