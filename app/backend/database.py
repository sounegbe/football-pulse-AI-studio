from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from app.backend.config import ROOT


def timestamp():
    return datetime.now(timezone.utc).isoformat()

class Database:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / 'studio.sqlite3'

    @contextmanager
    def transaction(self, write=False):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        try:
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.data_dir / 'assets').mkdir(exist_ok=True, mode=0o700)
        with self.transaction(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            versions = {r['version'] for r in db.execute('SELECT version FROM schema_migrations')}
            migrations = sorted((ROOT / 'app/migrations').glob('*.sql'))
            known = {int(p.name.split('_')[0]) for p in migrations}
            if not versions.issubset(known):
                raise RuntimeError('Database schema is newer than this application')
            for path in migrations:
                version = int(path.name.split('_')[0])
                if version in versions:
                    continue
                for statement in path.read_text().split(';'):
                    if statement.strip():
                        db.execute(statement)
                db.execute('INSERT INTO schema_migrations VALUES (?,?)', (version, timestamp()))
            db.execute("UPDATE jobs SET status='failed', error_code='worker_interrupted', updated_at=? WHERE status='running'", (timestamp(),))
            db.execute('DELETE FROM sessions WHERE expires_at <= unixepoch()')
        self.path.chmod(0o600)
