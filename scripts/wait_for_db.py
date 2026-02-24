"""
Wait for PostgreSQL to be ready before starting the app.
Retries every 2 seconds for up to 60 seconds.
"""
import os
import sys
import time
import psycopg2


def wait_for_db(max_retries: int = 30, delay: int = 2):
    database_url = os.environ.get('DATABASE_URL', '')

    # SQLite — nothing to wait for
    if not database_url or database_url.startswith('sqlite'):
        print('[wait_for_db] Using SQLite — skipping wait.')
        return

    print('[wait_for_db] Waiting for PostgreSQL...')

    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(database_url)
            conn.close()
            print(f'[wait_for_db] PostgreSQL ready after {attempt} attempt(s).')
            return
        except psycopg2.OperationalError as e:
            print(
                f'[wait_for_db] Attempt {attempt}/{max_retries} failed: {e}'
            )
            if attempt < max_retries:
                time.sleep(delay)

    print('[wait_for_db] Could not connect to PostgreSQL. Exiting.')
    sys.exit(1)


if __name__ == '__main__':
    wait_for_db()