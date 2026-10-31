import os
from threading import Lock
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from app.core.config import BACKEND_DIR
_pool = None
_pool_lock = Lock()


def connection_options():
    url = os.getenv('DATABASE_URL', '')
    if not url:
        raise RuntimeError('DATABASE_URL is required')
    # The supplied URL uses SQLAlchemy's driver suffix; libpq expects postgresql://.
    url = url.replace('postgresql+psycopg://', 'postgresql://', 1)
    options = conninfo_to_dict(url)
    options.setdefault('sslmode', os.getenv('DATABASE_SSLMODE', 'require'))
    options['connect_timeout'] = 5
    options['options'] = '-c statement_timeout=5000'
    options['application_name'] = 'kinu-tabi-local'
    return options


def connect():
    """Open a standalone connection for scripts and background jobs."""
    return psycopg.connect(**connection_options(), row_factory=dict_row)


def get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(kwargs={**connection_options(), 'row_factory': dict_row},
                                   min_size=1, max_size=5, timeout=10, open=True)
        return _pool


def close_pool():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def get_connection():
    with get_pool().connection() as connection:
        yield connection
