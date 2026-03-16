import sqlite3
from flask import g
import config


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(config.DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(config.DATABASE)
    db.execute('PRAGMA foreign_keys = ON')

    db.executescript('''
        CREATE TABLE IF NOT EXISTS category (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            color       TEXT NOT NULL DEFAULT '#6b7280',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS task (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            description     TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'todo'
                                CHECK(status IN ('todo', 'in_progress', 'done')),
            priority        TEXT NOT NULL DEFAULT 'medium'
                                CHECK(priority IN ('high', 'medium', 'low')),
            category_id     INTEGER REFERENCES category(id) ON DELETE SET NULL,
            position        INTEGER NOT NULL DEFAULT 0,
            is_delegated    INTEGER NOT NULL DEFAULT 0,
            assignee_name   TEXT DEFAULT '',
            assignee_email  TEXT DEFAULT '',
            delegation_sent_at  TEXT DEFAULT NULL,
            delegation_status   TEXT DEFAULT NULL
                                CHECK(delegation_status IS NULL OR
                                      delegation_status IN ('pending', 'acknowledged', 'completed')),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS note (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            content     TEXT DEFAULT '',
            category_id INTEGER REFERENCES category(id) ON DELETE SET NULL,
            is_pinned   INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS task_note (
            task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
            note_id INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, note_id)
        );

        CREATE TABLE IF NOT EXISTS note_link (
            source_id INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
            target_id INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
            PRIMARY KEY (source_id, target_id)
        );

        CREATE TABLE IF NOT EXISTS tag (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS task_tag (
            task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
            tag_id  INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS email_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
            direction    TEXT NOT NULL CHECK(direction IN ('sent', 'received')),
            subject      TEXT,
            body_snippet TEXT,
            recipient    TEXT,
            message_id   TEXT,
            processed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS contact (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            email      TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_task_status ON task(status);
        CREATE INDEX IF NOT EXISTS idx_task_category ON task(category_id);
        CREATE INDEX IF NOT EXISTS idx_task_priority ON task(priority);
        CREATE INDEX IF NOT EXISTS idx_task_delegated ON task(is_delegated);
        CREATE INDEX IF NOT EXISTS idx_task_position ON task(status, position);

        CREATE TRIGGER IF NOT EXISTS task_updated_at
            AFTER UPDATE ON task
            FOR EACH ROW
        BEGIN
            UPDATE task SET updated_at = datetime('now') WHERE id = OLD.id;
        END;
    ''')

    # Migrations: add columns to existing tables safely
    migrations = [
        "ALTER TABLE task ADD COLUMN due_date TEXT DEFAULT NULL",
        "ALTER TABLE note ADD COLUMN dummy_migrate INTEGER DEFAULT 0",
        # Federated sync fields
        "ALTER TABLE task ADD COLUMN is_remote INTEGER DEFAULT 0",
        "ALTER TABLE task ADD COLUMN remote_id INTEGER",
        "ALTER TABLE task ADD COLUMN remote_source TEXT DEFAULT ''",
        "ALTER TABLE task ADD COLUMN last_synced TEXT",
    ]
    for sql in migrations:
        try:
            db.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Note updated_at trigger
    db.executescript('''
        CREATE TRIGGER IF NOT EXISTS note_updated_at
            AFTER UPDATE ON note
            FOR EACH ROW
        BEGIN
            UPDATE note SET updated_at = datetime('now') WHERE id = OLD.id;
        END;

        CREATE INDEX IF NOT EXISTS idx_task_due_date ON task(due_date);
    ''')

    # Seed default categories
    defaults = [
        ('Work', '#4f46e5'),
        ('Personal', '#22c55e'),
        ('Ideas', '#f59e0b'),
    ]
    for name, color in defaults:
        db.execute(
            'INSERT OR IGNORE INTO category (name, color) VALUES (?, ?)',
            (name, color)
        )

    db.commit()
    db.close()
