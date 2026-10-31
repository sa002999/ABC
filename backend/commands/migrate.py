from app.core.config import BACKEND_DIR
from app.core.database import connect


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
