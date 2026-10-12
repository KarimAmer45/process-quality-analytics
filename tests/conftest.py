import os
import pathlib
import sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ingest'))
sys.path.insert(0,str(ROOT/'scripts'))
from common import connect

@pytest.fixture
def db():
    if not (os.environ.get('DATABASE_URL') or os.environ.get('PGDATABASE')):
        pytest.skip('Set DATABASE_URL or PGDATABASE for database integration tests')
    conn=connect('pytest_p2')
    try:yield conn
    finally:conn.rollback();conn.close()
