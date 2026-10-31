from app.core.database import connect
from psycopg.types.json import Jsonb


def seed_demo():
    with connect() as connection:
        for store_id, slug, city, name in [
            ('10000000-0000-4000-8000-000000000001', 'demo-tokyo', 'TOKYO', '東京測試門市'),
            ('10000000-0000-4000-8000-000000000002', 'demo-kyoto', 'KYOTO', '京都測試門市'),
        ]:
            connection.execute('''INSERT INTO stores (id, slug, city, name, languages, is_demo)
                VALUES (%s, %s, %s, %s, %s, true) ON CONFLICT DO NOTHING''',
                (store_id, slug, city, Jsonb({'zh-Hant': name}), ['zh-Hant', 'ja']))
    print('Demo stores are ready (clearly marked as development data).')
