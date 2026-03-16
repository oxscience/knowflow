"""
Background scheduler for automatic digest emails and reply checking.
Run alongside app.py: python scheduler.py
"""
import time
import sqlite3
import schedule

import config
from services.email_service import send_digest, check_replies, check_incoming_tasks, is_configured


def get_delegated_tasks_standalone():
    """Get delegated tasks without Flask context."""
    db = sqlite3.connect(config.DATABASE)
    db.row_factory = sqlite3.Row
    rows = db.execute('''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE t.is_delegated = 1 AND t.status != 'done'
              AND t.delegation_sent_at IS NULL
        ORDER BY t.priority DESC, t.created_at
    ''').fetchall()
    tasks = [dict(r) for r in rows]
    db.close()
    return tasks


def mark_sent_standalone(task_id, message_id=None):
    db = sqlite3.connect(config.DATABASE)
    db.execute('''
        UPDATE task SET delegation_sent_at = datetime('now'),
                        delegation_status = 'pending'
        WHERE id = ?
    ''', (task_id,))
    if message_id:
        email = db.execute('SELECT assignee_email FROM task WHERE id = ?', (task_id,)).fetchone()
        db.execute('''
            INSERT INTO email_log (task_id, direction, subject, message_id, recipient)
            VALUES (?, 'sent', ?, ?, ?)
        ''', (task_id, f'[KnowFlow #{task_id}]', message_id, email[0] if email else ''))
    db.commit()
    db.close()


def mark_completed_standalone(task_id, snippet='', from_addr=''):
    db = sqlite3.connect(config.DATABASE)
    db.execute('''
        UPDATE task SET status = 'done', delegation_status = 'completed'
        WHERE id = ?
    ''', (task_id,))
    db.execute('''
        INSERT INTO email_log (task_id, direction, body_snippet, recipient)
        VALUES (?, 'received', ?, ?)
    ''', (task_id, snippet[:200], from_addr))
    db.commit()
    db.close()


def run_digest():
    try:
        if not is_configured():
            print('[Scheduler] Email not configured, skipping digest.')
            return

        tasks = get_delegated_tasks_standalone()
        if not tasks:
            print('[Scheduler] No unsent delegated tasks.')
            return

        print(f'[Scheduler] Sending digest for {len(tasks)} task(s)...')
        results = send_digest(tasks)
        for r in results:
            if r['status'] == 'sent':
                mark_sent_standalone(r['task_id'], r.get('message_id'))
                print(f'  Task #{r["task_id"]}: sent')
            else:
                print(f'  Task #{r["task_id"]}: {r["status"]} - {r.get("reason", "")}')
    except Exception as e:
        print(f'[Scheduler] Digest error: {e}')


def run_check_replies():
    try:
        if not is_configured():
            return

        replies = check_replies()
        for reply in replies:
            if reply['completed']:
                mark_completed_standalone(
                    reply['task_id'],
                    snippet=reply.get('snippet', ''),
                    from_addr=reply.get('from', '')
                )
                print(f'[Scheduler] Task #{reply["task_id"]} completed via email from {reply["from"]}')

        if not replies:
            print('[Scheduler] No new replies.')
    except Exception as e:
        print(f'[Scheduler] Reply check error: {e}')


def import_remote_task_standalone(data):
    """Import a task from another KnowFlow instance (without Flask context)."""
    db = sqlite3.connect(config.DATABASE)
    db.row_factory = sqlite3.Row

    # Check if already imported
    existing = db.execute(
        'SELECT id FROM task WHERE is_remote = 1 AND remote_id = ? AND remote_source = ?',
        (data['remote_id'], data['remote_source'])
    ).fetchone()
    if existing:
        db.close()
        return None

    # Match category by name
    cat_id = None
    if data.get('category_name'):
        cat = db.execute('SELECT id FROM category WHERE name = ?', (data['category_name'],)).fetchone()
        if cat:
            cat_id = cat['id']

    # Get next position
    pos = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM task WHERE status = 'todo'"
    ).fetchone()[0]

    db.execute('''
        INSERT INTO task (title, description, priority, category_id, position,
                         is_remote, remote_id, remote_source, last_synced, due_date)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, datetime('now'), ?)
    ''', (data['title'], data.get('description', ''), data.get('priority', 'medium'),
          cat_id, pos, data['remote_id'], data['remote_source'],
          data.get('due_date')))
    db.commit()
    task_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.close()
    return task_id


def update_task_status_standalone(task_id, new_status):
    """Update task status (without Flask context)."""
    db = sqlite3.connect(config.DATABASE)
    db.execute('UPDATE task SET status = ? WHERE id = ?', (new_status, task_id))
    if new_status == 'done':
        db.execute('''
            UPDATE task SET delegation_status = 'completed' WHERE id = ?
        ''', (task_id,))
    db.commit()
    db.close()


def run_sync_inbox():
    """Check inbox for incoming KnowFlow tasks and status updates."""
    try:
        if not is_configured():
            return

        incoming = check_incoming_tasks()
        for item in incoming:
            if item['type'] == 'task_delegation':
                task_id = import_remote_task_standalone(item)
                if task_id:
                    print(f'[Scheduler] Imported remote task #{task_id}: {item["title"]} (from {item["remote_source"]})')

            elif item['type'] == 'status_update':
                task_id = item['remote_task_id']
                new_status = item['new_status']
                if new_status in ('todo', 'in_progress', 'done'):
                    update_task_status_standalone(task_id, new_status)
                    print(f'[Scheduler] Task #{task_id} status updated to {new_status} by {item["sender_email"]}')

        if not incoming:
            print('[Scheduler] No incoming sync data.')
    except Exception as e:
        print(f'[Scheduler] Sync error: {e}')


if __name__ == '__main__':
    day = config.DIGEST_DAY.lower()
    time_str = config.DIGEST_TIME

    scheduler_fn = getattr(schedule.every(), day)
    scheduler_fn.at(time_str).do(run_digest)

    schedule.every(15).minutes.do(run_check_replies)
    schedule.every(10).minutes.do(run_sync_inbox)

    print(f'[Scheduler] Digest scheduled for {day} at {time_str}')
    print(f'[Scheduler] Reply check every 15 minutes')
    print(f'[Scheduler] Inbox sync every 10 minutes')
    print(f'[Scheduler] Email configured: {is_configured()}')
    print('[Scheduler] Running... (Ctrl+C to stop)')

    while True:
        schedule.run_pending()
        time.sleep(30)
