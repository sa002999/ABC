"""Explicit database setup; never create tables or seed records during HTTP startup."""
import argparse
import sys

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
import httpx
from psycopg.types.json import Jsonb

from database import BACKEND_DIR, connect


def migrate():
    with connect() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(72618401)')
        connection.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
        )''')
        applied = {row['version'] for row in connection.execute('SELECT version FROM schema_migrations')}
        for path in sorted((BACKEND_DIR / 'migrations').glob('*.sql')):
            if path.name not in applied:
                connection.execute(path.read_text(encoding='utf-8'))
                connection.execute('INSERT INTO schema_migrations (version) VALUES (%s)', (path.name,))
                print('Applied:', path.name)
    print('Database migrations are up to date.')


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


def check():
    with connect() as connection:
        connection.execute('SELECT 1').fetchone()
    print('PostgreSQL connection: OK')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['check', 'check-react', 'configure-react-cors', 'migrate', 'seed-demo', 'seed-catalog', 'publish-catalog', 'seed-models', 'check-photo-storage', 'cleanup-photo-uploads', 'try-on-worker', 'cleanup-generations', 'seed-booking-demo', 'cleanup-booking-holds'])
    arguments = parser.parse_args()
    try:
        if arguments.command == 'configure-react-cors':
            from check_react import configure_react_cors
            configure_react_cors()
        elif arguments.command == 'check-react':
            from check_react import check_react
            check_react()
        elif arguments.command == 'seed-booking-demo':
            from seed_booking import seed_booking
            seed_booking()
        elif arguments.command == 'cleanup-booking-holds':
            from bookings import cleanup_booking_holds
            cleanup_booking_holds()
            print('Expired booking holds released; pending payments preserved.')
        elif arguments.command == 'try-on-worker':
            from generations import worker
            try:
                worker()
            except KeyboardInterrupt:
                print('Try-on worker stopped.')
        elif arguments.command == 'cleanup-generations':
            from generations import cleanup_results
            cleanup_results()
            print('Generation cleanup batch completed.')
        elif arguments.command == 'seed-models':
            from person_sources import seed_models
            seed_models()
        elif arguments.command == 'check-photo-storage':
            from photo_storage import ensure_private_storage, check_upload_cors
            import os
            ensure_private_storage()
            check_upload_cors(os.getenv('PUBLIC_ORIGIN'))
            print('Private photo storage and local upload CORS: OK')
        elif arguments.command == 'cleanup-photo-uploads':
            from person_sources import cleanup_photos
            if not cleanup_photos():
                raise RuntimeError('Photo cleanup could not finish; pending rows were preserved for retry')
            print('Photo cleanup batch completed (maximum 100 rows).')
        elif arguments.command == 'publish-catalog':
            from storage import publish_catalog
            publish_catalog()
        elif arguments.command == 'seed-catalog':
            from seed_catalog import seed_catalog
            seed_catalog()
        else:
            {'check': check, 'migrate': migrate, 'seed-demo': seed_demo}[arguments.command]()
    except (psycopg.Error, RuntimeError, ValueError, OSError, BotoCoreError, ClientError, httpx.HTTPError) as error:
        # Connection exceptions may contain credentials or private endpoints.
        code = error.response['Error']['Code'] if isinstance(error, ClientError) else type(error).__name__
        print('Operation failed (' + code + '). Check database/AWS settings, connectivity and permissions.', file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        sys.exit(1)
