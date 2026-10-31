from app.core.database import connect


def check():
    with connect() as connection:
        connection.execute('SELECT 1').fetchone()
    print('PostgreSQL connection: OK')
