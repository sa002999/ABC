"""Explicit maintenance commands; HTTP startup never writes schema or seeds."""
import argparse
import sys
import httpx
import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from commands.migrate import migrate
from commands.seeds.stores import seed_demo
from commands.maintenance.database import check
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['check', 'check-react', 'configure-react-cors', 'migrate', 'seed-demo', 'seed-catalog', 'publish-catalog', 'seed-models', 'check-photo-storage', 'cleanup-photo-uploads', 'try-on-worker', 'cleanup-generations', 'seed-booking-demo', 'cleanup-booking-holds', 'payment-reconcile'])
    arguments = parser.parse_args()
    try:
        if arguments.command == 'payment-reconcile':
            import time
            from app.modules.bookings.payments import reconcile_batch
            while True:
                try: reconcile_batch()
                except psycopg.Error: print('Payment reconciliation unavailable; original orders preserved.',flush=True)
                time.sleep(15)
        elif arguments.command == 'configure-react-cors':
            from commands.maintenance.react import configure_react_cors
            configure_react_cors()
        elif arguments.command == 'check-react':
            from commands.maintenance.react import check_react
            check_react()
        elif arguments.command == 'seed-booking-demo':
            from commands.seeds.bookings import seed_booking
            seed_booking()
        elif arguments.command == 'cleanup-booking-holds':
            from app.modules.bookings.service import cleanup_booking_holds
            cleanup_booking_holds()
            print('Expired booking holds released; pending payments preserved.')
        elif arguments.command == 'try-on-worker':
            from app.modules.try_on.worker import worker
            try:
                worker()
            except KeyboardInterrupt:
                print('Try-on worker stopped.')
        elif arguments.command == 'cleanup-generations':
            from app.modules.try_on.worker import cleanup_results
            cleanup_results()
            print('Generation cleanup batch completed.')
        elif arguments.command == 'seed-models':
            from commands.seeds.models import seed_models
            seed_models()
        elif arguments.command == 'check-photo-storage':
            from app.integrations.s3 import ensure_private_storage, check_upload_cors
            import os
            ensure_private_storage()
            check_upload_cors(os.getenv('PUBLIC_ORIGIN'))
            print('Private photo storage and local upload CORS: OK')
        elif arguments.command == 'cleanup-photo-uploads':
            from app.modules.try_on.photos import cleanup_photos
            if not cleanup_photos():
                raise RuntimeError('Photo cleanup could not finish; pending rows were preserved for retry')
            print('Photo cleanup batch completed (maximum 100 rows).')
        elif arguments.command == 'publish-catalog':
            from commands.maintenance.publish_catalog import publish_catalog
            publish_catalog()
        elif arguments.command == 'seed-catalog':
            from commands.seeds.catalog import seed_catalog
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
