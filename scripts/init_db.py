import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db

app = create_app('development')

with app.app_context():
    db.create_all()
    print('✅ All tables created:')
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    for table in inspector.get_table_names():
        print(f'   • {table}')