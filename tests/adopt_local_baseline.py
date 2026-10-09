"""Verified, additive adoption of an existing exact baseline (explicit opt-in).

Creates a separate schema reference, compares every table/column/index/FK,
backs up all existing schema/data locally, then stamps and upgrades. No DROP,
TRUNCATE, password changes, or seed data on the application database.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def canonical(value):
    return json.dumps(value, default=str, sort_keys=True)


def signature(inspector, table):
    columns = [{key: str(c[key]) if key == 'type' else c.get(key)
                for key in ('name', 'type', 'nullable', 'default', 'autoincrement')}
               for c in inspector.get_columns(table)]
    indexes = sorted(inspector.get_indexes(table), key=lambda x: x['name'])
    fks = sorted(inspector.get_foreign_keys(table), key=lambda x: x['name'])
    checks = sorted(inspector.get_check_constraints(table), key=lambda x: x['name'] or '')
    return canonical([columns, inspector.get_pk_constraint(table), indexes, fks, checks])


def main():
    if os.getenv('RUN_VERIFIED_LOCAL_UPGRADE') != '1':
        raise RuntimeError('Explicit verified additive upgrade opt-in required')
    from config import load_config
    from sqlalchemy import create_engine, inspect, text, MetaData, Table
    root = Path(__file__).resolve().parents[1]
    url = load_config()['SQLALCHEMY_DATABASE_URI']
    if not url.database or url.database.endswith('_test'):
        raise RuntimeError('Expected configured application database, not a QA database')
    live = create_engine(url)
    inspector = inspect(live)
    tables = inspector.get_table_names()
    if 'alembic_version' in tables or 'activity_tracking' in tables:
        raise RuntimeError('Adoption only supports an untouched legacy baseline; use normal upgrade for versioned DB')
    reference_name = 'wakaf_baseline_' + uuid4().hex[:12] + '_test'
    server = create_engine(url.set(database=None))
    with server.begin() as connection:
        connection.execute(text(f'CREATE DATABASE `{reference_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci'))
    reference = create_engine(url.set(database=reference_name))
    spec = importlib.util.spec_from_file_location('baseline_snapshot', root / 'migrations/versions/0001_baseline.py')
    baseline = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)
    sql = '\n'.join(line for line in baseline.SQL.splitlines() if not line.lstrip().startswith('--'))
    with reference.begin() as connection:
        for statement in sql.split(';'):
            if statement.strip():
                connection.execute(text(statement))
    expected = inspect(reference)
    if sorted(tables) != sorted(expected.get_table_names()):
        raise RuntimeError('Table inventory differs from baseline; nothing stamped or altered')
    mismatches = [table for table in tables if signature(inspector, table) != signature(expected, table)]
    if mismatches:
        raise RuntimeError('Baseline differs in: ' + ', '.join(mismatches) + '; nothing stamped or altered')
    folder = Path(mkdtemp(prefix='wakaf-pre-migration-backup-'))
    backup = folder / 'database.sql'
    before = {}
    # Snapshot and dump avoid writing account data to terminal or repository.
    with live.connect().execution_options(isolation_level='REPEATABLE READ') as connection, connection.begin(), backup.open('w', encoding='utf-8') as output:
        output.write('-- Restore ONLY into a new empty database. No DROP or reset commands.\nSET FOREIGN_KEY_CHECKS=0;\n')
        for name in tables:
            output.write(connection.execute(text(f'SHOW CREATE TABLE `{name}`')).one()[1] + ';\n')
            table = Table(name, MetaData(), autoload_with=connection)
            rows = connection.execute(table.select()).mappings().all()
            before[name] = len(rows)
            for row in rows:
                statement = table.insert().values(dict(row)).compile(dialect=live.dialect, compile_kwargs={'literal_binds': True})
                output.write(str(statement) + ';\n')
        output.write('SET FOREIGN_KEY_CHECKS=1;\n')
    if not backup.stat().st_size:
        raise RuntimeError('Empty backup; nothing altered')
    for args in (('stamp', '0001_baseline'), ('upgrade',)):
        result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'db', *args], cwd=root, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Migration step failed; DDL may be partial. Backup: ' + str(backup))
    with live.connect() as connection:
        revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
        after = {name: connection.execute(text(f'SELECT COUNT(*) FROM `{name}`')).scalar() for name in tables}
        if before != after:
            raise RuntimeError('Row counts changed; inspect concurrent writers. Backup: ' + str(backup))
    print(json.dumps({'baseline_tables_verified': len(tables), 'revision': revision,
        'row_counts_preserved': True, 'backup': str(backup), 'reference_database': reference_name}))
    reference.dispose(); live.dispose(); server.dispose()


if __name__ == '__main__':
    main()
