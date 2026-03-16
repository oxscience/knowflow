import re
from markupsafe import Markup, escape
from database import get_db


# --- Categories ---

def get_categories():
    db = get_db()
    return db.execute('SELECT * FROM category ORDER BY name').fetchall()


def create_category(name, color='#6b7280'):
    db = get_db()
    db.execute('INSERT INTO category (name, color) VALUES (?, ?)', (name, color))
    db.commit()
    return db.execute('SELECT * FROM category WHERE id = last_insert_rowid()').fetchone()


def delete_category(category_id):
    db = get_db()
    db.execute('DELETE FROM category WHERE id = ?', (category_id,))
    db.commit()


# --- Tags ---

def get_tags():
    db = get_db()
    return db.execute('SELECT * FROM tag ORDER BY name').fetchall()


def get_or_create_tag(name):
    db = get_db()
    name = name.strip().lower()
    tag = db.execute('SELECT * FROM tag WHERE name = ?', (name,)).fetchone()
    if tag:
        return tag
    db.execute('INSERT INTO tag (name) VALUES (?)', (name,))
    db.commit()
    return db.execute('SELECT * FROM tag WHERE id = last_insert_rowid()').fetchone()


def get_task_tags(task_id):
    db = get_db()
    return db.execute('''
        SELECT t.name FROM tag t
        JOIN task_tag tt ON t.id = tt.tag_id
        WHERE tt.task_id = ?
        ORDER BY t.name
    ''', (task_id,)).fetchall()


def set_task_tags(task_id, tag_names):
    db = get_db()
    db.execute('DELETE FROM task_tag WHERE task_id = ?', (task_id,))
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        tag = get_or_create_tag(name)
        db.execute('INSERT OR IGNORE INTO task_tag (task_id, tag_id) VALUES (?, ?)',
                   (task_id, tag['id']))
    db.commit()


# --- Tasks ---

def _task_with_extras(row):
    """Convert a task row to a dict with category and tag info."""
    if row is None:
        return None
    task = dict(row)
    task['tags'] = [t['name'] for t in get_task_tags(task['id'])]
    return task


def get_next_position(status):
    db = get_db()
    result = db.execute(
        'SELECT COALESCE(MAX(position), -1) + 1 FROM task WHERE status = ?',
        (status,)
    ).fetchone()
    return result[0]


def create_task(title, priority='medium', category_id=None, description='',
                is_delegated=False, assignee_name='', assignee_email='', tags=None,
                due_date=None):
    db = get_db()
    position = get_next_position('todo')
    cat_id = int(category_id) if category_id else None

    db.execute('''
        INSERT INTO task (title, description, priority, category_id, position,
                         is_delegated, assignee_name, assignee_email, due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, description, priority, cat_id, position,
          1 if is_delegated else 0, assignee_name, assignee_email,
          due_date or None))
    db.commit()

    task_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    if tags:
        set_task_tags(task_id, tags)

    return get_task(task_id)


def get_task(task_id):
    db = get_db()
    row = db.execute('''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()
    return _task_with_extras(row)


def get_tasks_by_status(status=None):
    db = get_db()
    if status:
        rows = db.execute('''
            SELECT t.*, c.name as category_name, c.color as category_color
            FROM task t
            LEFT JOIN category c ON t.category_id = c.id
            WHERE t.status = ?
            ORDER BY CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, t.position
        ''', (status,)).fetchall()
    else:
        rows = db.execute('''
            SELECT t.*, c.name as category_name, c.color as category_color
            FROM task t
            LEFT JOIN category c ON t.category_id = c.id
            ORDER BY CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, t.position
        ''').fetchall()
    return [_task_with_extras(r) for r in rows]


def get_all_tasks_grouped():
    return {
        'todo': get_tasks_by_status('todo'),
        'in_progress': get_tasks_by_status('in_progress'),
        'done': get_tasks_by_status('done'),
    }


def update_task(task_id, **kwargs):
    db = get_db()
    allowed = {'title', 'description', 'priority', 'category_id', 'status',
               'position', 'is_delegated', 'assignee_name', 'assignee_email', 'due_date'}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

    if 'category_id' in fields:
        fields['category_id'] = int(fields['category_id']) if fields['category_id'] else None
    if 'is_delegated' in fields:
        fields['is_delegated'] = 1 if fields['is_delegated'] else 0

    if fields:
        set_clause = ', '.join(f'{k} = ?' for k in fields)
        values = list(fields.values()) + [task_id]
        db.execute(f'UPDATE task SET {set_clause} WHERE id = ?', values)
        db.commit()

    if 'tags' in kwargs:
        set_task_tags(task_id, kwargs['tags'])

    return get_task(task_id)


def update_task_status(task_id, new_status, new_position):
    db = get_db()
    task = db.execute('SELECT status, position FROM task WHERE id = ?', (task_id,)).fetchone()
    if not task:
        return None

    old_status = task['status']

    # Shift positions in the old column
    if old_status != new_status:
        db.execute('''
            UPDATE task SET position = position - 1
            WHERE status = ? AND position > ?
        ''', (old_status, task['position']))

    # Shift positions in the new column to make room
    db.execute('''
        UPDATE task SET position = position + 1
        WHERE status = ? AND position >= ? AND id != ?
    ''', (new_status, new_position, task_id))

    db.execute('''
        UPDATE task SET status = ?, position = ? WHERE id = ?
    ''', (new_status, new_position, task_id))
    db.commit()

    return get_task(task_id)


def delete_task(task_id):
    db = get_db()
    task = db.execute('SELECT status, position FROM task WHERE id = ?', (task_id,)).fetchone()
    if task:
        db.execute('DELETE FROM task WHERE id = ?', (task_id,))
        db.execute('''
            UPDATE task SET position = position - 1
            WHERE status = ? AND position > ?
        ''', (task['status'], task['position']))
        db.commit()
        return True
    return False


def get_delegated_tasks(unsent_only=False):
    """Get all tasks marked as delegated."""
    db = get_db()
    sql = '''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE t.is_delegated = 1 AND t.status != 'done'
    '''
    if unsent_only:
        sql += ' AND t.delegation_sent_at IS NULL'
    sql += ' ORDER BY t.priority DESC, t.created_at'
    rows = db.execute(sql).fetchall()
    return [_task_with_extras(r) for r in rows]


def mark_delegation_sent(task_id, message_id=None):
    db = get_db()
    db.execute('''
        UPDATE task SET delegation_sent_at = datetime('now'),
                        delegation_status = 'pending'
        WHERE id = ?
    ''', (task_id,))
    if message_id:
        db.execute('''
            INSERT INTO email_log (task_id, direction, subject, message_id, recipient)
            VALUES (?, 'sent', ?, ?, ?)
        ''', (task_id,
              f'[KnowFlow #{task_id}]',
              message_id,
              db.execute('SELECT assignee_email FROM task WHERE id = ?', (task_id,)).fetchone()[0]))
    db.commit()


def mark_delegation_completed(task_id, snippet='', from_addr=''):
    db = get_db()
    db.execute('''
        UPDATE task SET status = 'done', delegation_status = 'completed'
        WHERE id = ?
    ''', (task_id,))
    db.execute('''
        INSERT INTO email_log (task_id, direction, body_snippet, recipient)
        VALUES (?, 'received', ?, ?)
    ''', (task_id, snippet[:200], from_addr))
    db.commit()
    return get_task(task_id)


def get_email_log(task_id=None, limit=50):
    db = get_db()
    if task_id:
        rows = db.execute(
            'SELECT * FROM email_log WHERE task_id = ? ORDER BY processed_at DESC LIMIT ?',
            (task_id, limit)
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT * FROM email_log ORDER BY processed_at DESC LIMIT ?',
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_overdue_tasks():
    db = get_db()
    rows = db.execute('''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE t.due_date IS NOT NULL AND t.due_date < date('now')
              AND t.status != 'done'
        ORDER BY t.due_date
    ''').fetchall()
    return [_task_with_extras(r) for r in rows]


def get_upcoming_tasks(days=7):
    db = get_db()
    rows = db.execute('''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE t.due_date IS NOT NULL
              AND t.due_date >= date('now')
              AND t.due_date <= date('now', '+' || ? || ' days')
              AND t.status != 'done'
        ORDER BY t.due_date
    ''', (days,)).fetchall()
    return [_task_with_extras(r) for r in rows]


# --- Notes ---

def create_note(title, content='', category_id=None, is_pinned=False):
    db = get_db()
    cat_id = int(category_id) if category_id else None
    db.execute('''
        INSERT INTO note (title, content, category_id, is_pinned)
        VALUES (?, ?, ?, ?)
    ''', (title, content, cat_id, 1 if is_pinned else 0))
    db.commit()
    note_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    return get_note(note_id)


def get_note(note_id):
    db = get_db()
    row = db.execute('''
        SELECT n.*, c.name as category_name, c.color as category_color
        FROM note n
        LEFT JOIN category c ON n.category_id = c.id
        WHERE n.id = ?
    ''', (note_id,)).fetchone()
    if row is None:
        return None
    note = dict(row)
    note['linked_tasks'] = get_note_tasks(note_id)
    return note


def get_all_notes(category_id=None):
    db = get_db()
    sql = '''
        SELECT n.*, c.name as category_name, c.color as category_color
        FROM note n
        LEFT JOIN category c ON n.category_id = c.id
        WHERE 1=1
    '''
    params = []
    if category_id:
        sql += ' AND n.category_id = ?'
        params.append(int(category_id))
    sql += ' ORDER BY n.is_pinned DESC, n.updated_at DESC'
    rows = db.execute(sql, params).fetchall()
    notes = []
    for r in rows:
        note = dict(r)
        note['linked_tasks'] = get_note_tasks(note['id'])
        notes.append(note)
    return notes


def update_note(note_id, **kwargs):
    db = get_db()
    allowed = {'title', 'content', 'category_id', 'is_pinned'}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if 'category_id' in fields:
        fields['category_id'] = int(fields['category_id']) if fields['category_id'] else None
    if 'is_pinned' in fields:
        fields['is_pinned'] = 1 if fields['is_pinned'] else 0
    if fields:
        set_clause = ', '.join(f'{k} = ?' for k in fields)
        values = list(fields.values()) + [note_id]
        db.execute(f'UPDATE note SET {set_clause} WHERE id = ?', values)
        db.commit()
    return get_note(note_id)


def delete_note(note_id):
    db = get_db()
    db.execute('DELETE FROM note WHERE id = ?', (note_id,))
    db.commit()


def link_task_to_note(task_id, note_id):
    db = get_db()
    db.execute('INSERT OR IGNORE INTO task_note (task_id, note_id) VALUES (?, ?)',
               (task_id, note_id))
    db.commit()


def unlink_task_from_note(task_id, note_id):
    db = get_db()
    db.execute('DELETE FROM task_note WHERE task_id = ? AND note_id = ?',
               (task_id, note_id))
    db.commit()


def get_note_tasks(note_id):
    db = get_db()
    rows = db.execute('''
        SELECT t.id, t.title, t.status, t.priority FROM task t
        JOIN task_note tn ON t.id = tn.task_id
        WHERE tn.note_id = ?
        ORDER BY t.status, t.position
    ''', (note_id,)).fetchall()
    return [dict(r) for r in rows]


def search_notes(query=''):
    db = get_db()
    like = f'%{query}%'
    rows = db.execute('''
        SELECT n.*, c.name as category_name, c.color as category_color
        FROM note n
        LEFT JOIN category c ON n.category_id = c.id
        WHERE n.title LIKE ? OR n.content LIKE ?
        ORDER BY n.is_pinned DESC, n.updated_at DESC
    ''', (like, like)).fetchall()
    notes = []
    for r in rows:
        note = dict(r)
        note['linked_tasks'] = get_note_tasks(note['id'])
        notes.append(note)
    return notes


# --- Wiki Links (Obsidian-style) ---

WIKI_LINK_RE = re.compile(r'\[\[(.+?)\]\]')


def parse_wiki_links(content):
    """Extract all [[Title]] references from content."""
    return WIKI_LINK_RE.findall(content or '')


def update_note_links(note_id, content):
    """Parse content for [[...]] links and update the note_link table."""
    db = get_db()
    db.execute('DELETE FROM note_link WHERE source_id = ?', (note_id,))
    titles = parse_wiki_links(content)
    for title in set(titles):
        target = db.execute('SELECT id FROM note WHERE title = ? COLLATE NOCASE',
                            (title,)).fetchone()
        if target and target['id'] != note_id:
            db.execute('INSERT OR IGNORE INTO note_link (source_id, target_id) VALUES (?, ?)',
                       (note_id, target['id']))
    db.commit()


def get_backlinks(note_id):
    """Get all notes that link TO this note."""
    db = get_db()
    rows = db.execute('''
        SELECT n.id, n.title FROM note n
        JOIN note_link nl ON n.id = nl.source_id
        WHERE nl.target_id = ?
        ORDER BY n.title
    ''', (note_id,)).fetchall()
    return [dict(r) for r in rows]


def get_forward_links(note_id):
    """Get all notes this note links TO."""
    db = get_db()
    rows = db.execute('''
        SELECT n.id, n.title FROM note n
        JOIN note_link nl ON n.id = nl.target_id
        WHERE nl.source_id = ?
        ORDER BY n.title
    ''', (note_id,)).fetchall()
    return [dict(r) for r in rows]


def render_wiki_links(content):
    """Replace [[Title]] with clickable HTML links. Returns Markup (safe HTML)."""
    if not content:
        return ''
    db = get_db()

    def replace_link(match):
        title = match.group(1)
        target = db.execute('SELECT id FROM note WHERE title = ? COLLATE NOCASE',
                            (title,)).fetchone()
        escaped_title = escape(title)
        if target:
            return f'<a href="/notes/{target["id"]}" class="wiki-link">{escaped_title}</a>'
        return f'<a href="/notes/new?title={escaped_title}" class="wiki-link wiki-link-new">{escaped_title}</a>'

    escaped = str(escape(content))
    result = re.sub(r'\[\[(.+?)\]\]', lambda m: replace_link(m), escaped)
    return Markup(result)


def get_note_title_map():
    """Return {lowercase_title: {id, title}} for all notes."""
    db = get_db()
    rows = db.execute('SELECT id, title FROM note').fetchall()
    return {r['title'].lower(): {'id': r['id'], 'title': r['title']} for r in rows}


def get_graph_data():
    """Return all notes and their links as graph-ready data."""
    db = get_db()
    notes = db.execute('''
        SELECT n.id, n.title, c.name as category_name, c.color as category_color
        FROM note n
        LEFT JOIN category c ON n.category_id = c.id
        ORDER BY n.title
    ''').fetchall()

    links = db.execute('SELECT source_id, target_id FROM note_link').fetchall()

    # Count connections per note
    link_count = {}
    for link in links:
        link_count[link['source_id']] = link_count.get(link['source_id'], 0) + 1
        link_count[link['target_id']] = link_count.get(link['target_id'], 0) + 1

    nodes = [{
        'id': n['id'],
        'title': n['title'],
        'category': n['category_name'] or '',
        'color': n['category_color'] or '#6b7280',
        'connections': link_count.get(n['id'], 0),
    } for n in notes]

    edges = [{
        'source': l['source_id'],
        'target': l['target_id'],
    } for l in links]

    return {'nodes': nodes, 'edges': edges}


# --- Contacts ---

def get_contacts():
    db = get_db()
    return db.execute('SELECT * FROM contact ORDER BY name').fetchall()


def get_or_create_contact(name, email):
    db = get_db()
    email = email.strip().lower()
    name = name.strip()
    existing = db.execute('SELECT * FROM contact WHERE email = ?', (email,)).fetchone()
    if existing:
        # Update name if changed
        if name and name != existing['name']:
            db.execute('UPDATE contact SET name = ? WHERE id = ?', (name, existing['id']))
            db.commit()
            return db.execute('SELECT * FROM contact WHERE id = ?', (existing['id'],)).fetchone()
        return existing
    db.execute('INSERT INTO contact (name, email) VALUES (?, ?)', (name or email, email))
    db.commit()
    return db.execute('SELECT * FROM contact WHERE id = last_insert_rowid()').fetchone()


def delete_contact(contact_id):
    db = get_db()
    db.execute('DELETE FROM contact WHERE id = ?', (contact_id,))
    db.commit()


# --- Remote / Federated Sync ---

def create_remote_task(remote_id, remote_source, title, description='',
                       priority='medium', due_date=None, category_name=None, tags=None):
    """Create a task received from another KnowFlow instance."""
    db = get_db()
    position = get_next_position('todo')
    # Try to match category by name
    cat_id = None
    if category_name:
        cat = db.execute('SELECT id FROM category WHERE name = ?', (category_name,)).fetchone()
        if cat:
            cat_id = cat['id']

    db.execute('''
        INSERT INTO task (title, description, priority, category_id, position,
                         is_remote, remote_id, remote_source, last_synced, due_date)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, datetime('now'), ?)
    ''', (title, description, priority, cat_id, position,
          remote_id, remote_source, due_date or None))
    db.commit()
    task_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    if tags:
        set_task_tags(task_id, tags)
    return get_task(task_id)


def get_remote_task(remote_id, remote_source):
    """Find a local task that was imported from a specific remote source."""
    db = get_db()
    row = db.execute('''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE t.is_remote = 1 AND t.remote_id = ? AND t.remote_source = ?
    ''', (remote_id, remote_source)).fetchone()
    return _task_with_extras(row)


def get_received_tasks():
    """Get all tasks received from other KnowFlow instances."""
    db = get_db()
    rows = db.execute('''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE t.is_remote = 1
        ORDER BY t.status, t.created_at DESC
    ''').fetchall()
    return [_task_with_extras(r) for r in rows]


def update_remote_sync(task_id):
    """Mark a remote task as recently synced."""
    db = get_db()
    db.execute('UPDATE task SET last_synced = datetime(\'now\') WHERE id = ?', (task_id,))
    db.commit()


def search_tasks(query='', status=None, priority=None, category_id=None, delegated=None):
    db = get_db()
    sql = '''
        SELECT t.*, c.name as category_name, c.color as category_color
        FROM task t
        LEFT JOIN category c ON t.category_id = c.id
        WHERE 1=1
    '''
    params = []

    if query:
        sql += ' AND (t.title LIKE ? OR t.description LIKE ?)'
        like = f'%{query}%'
        params.extend([like, like])
    if status:
        sql += ' AND t.status = ?'
        params.append(status)
    if priority:
        sql += ' AND t.priority = ?'
        params.append(priority)
    if category_id:
        sql += ' AND t.category_id = ?'
        params.append(int(category_id))
    if delegated is not None:
        sql += ' AND t.is_delegated = ?'
        params.append(1 if delegated else 0)

    sql += ' ORDER BY t.status, t.position'
    rows = db.execute(sql, params).fetchall()
    return [_task_with_extras(r) for r in rows]
