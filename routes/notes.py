from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from models import (
    create_note, get_note, get_all_notes, update_note, delete_note,
    search_notes, link_task_to_note, unlink_task_from_note,
    get_categories, search_tasks,
    update_note_links, get_backlinks, render_wiki_links, get_graph_data,
    get_note_title_map
)

notes_bp = Blueprint('notes', __name__)


def _sidebar_context(active_note_id=None):
    """Common context for all wiki pages (sidebar data)."""
    all_notes = get_all_notes()
    pinned = [n for n in all_notes if n.get('is_pinned')]
    unpinned = [n for n in all_notes if not n.get('is_pinned')]
    # Group by category, sorted by name (empty string → "Uncategorized" at end)
    grouped = {}
    for n in unpinned:
        cat = n.get('category_name') or ''
        grouped.setdefault(cat, []).append(n)
    sorted_groups = sorted(grouped.items(), key=lambda x: (x[0] == '', x[0]))
    return {
        'sidebar_notes': all_notes,
        'sidebar_pinned': pinned,
        'sidebar_groups': sorted_groups,
        'active_note_id': active_note_id,
        'categories': get_categories(),
    }


@notes_bp.route('/notes')
def index():
    notes = get_all_notes()
    ctx = _sidebar_context()
    return render_template('notes.html', notes=notes, active='notes',
                           render_wiki_links=render_wiki_links, **ctx)


@notes_bp.route('/notes/graph')
def graph():
    return redirect(url_for('notes.index'))


@notes_bp.route('/notes/new')
def new():
    prefill_title = request.args.get('title', '')
    ctx = _sidebar_context()
    return render_template('note_editor.html', note=None,
                           active='notes', prefill_title=prefill_title, **ctx)


@notes_bp.route('/notes', methods=['POST'])
def create():
    title = request.form.get('title', '').strip()
    if not title:
        title = 'Untitled Note'
    content = request.form.get('content', '')
    category_id = request.form.get('category_id') or None
    is_pinned = request.form.get('is_pinned') == 'on'

    note = create_note(title=title, content=content, category_id=category_id,
                       is_pinned=is_pinned)
    update_note_links(note['id'], content)

    if request.headers.get('HX-Request'):
        return render_template('partials/note_card.html', note=note,
                               render_wiki_links=render_wiki_links)

    ctx = _sidebar_context(active_note_id=note['id'])
    return render_template('note_editor.html', note=note,
                           active='notes', saved=True, backlinks=get_backlinks(note['id']),
                           render_wiki_links=render_wiki_links, **ctx)


@notes_bp.route('/notes/<int:note_id>')
def detail(note_id):
    note = get_note(note_id)
    if not note:
        return '', 404
    backlinks = get_backlinks(note_id)
    ctx = _sidebar_context(active_note_id=note_id)
    return render_template('note_editor.html', note=note,
                           active='notes', backlinks=backlinks,
                           render_wiki_links=render_wiki_links, **ctx)


@notes_bp.route('/notes/<int:note_id>', methods=['PUT'])
def update(note_id):
    data = request.form
    note = update_note(
        note_id,
        title=data.get('title'),
        content=data.get('content'),
        category_id=data.get('category_id') or None,
        is_pinned=data.get('is_pinned') == 'on',
    )
    if not note:
        return '', 404
    update_note_links(note_id, note['content'])

    backlinks = get_backlinks(note_id)
    ctx = _sidebar_context(active_note_id=note_id)
    return render_template('note_editor.html', note=note,
                           active='notes', saved=True, backlinks=backlinks,
                           render_wiki_links=render_wiki_links, **ctx)


@notes_bp.route('/notes/<int:note_id>', methods=['DELETE'])
def delete(note_id):
    delete_note(note_id)
    return '', 200, {'HX-Redirect': '/notes'}


@notes_bp.route('/notes/<int:note_id>/link-task', methods=['POST'])
def link_task(note_id):
    task_id = request.form.get('task_id')
    if task_id:
        link_task_to_note(int(task_id), note_id)
    note = get_note(note_id)
    return render_template('partials/linked_tasks.html', note=note)


@notes_bp.route('/notes/<int:note_id>/unlink-task/<int:task_id>', methods=['DELETE'])
def unlink_task(note_id, task_id):
    unlink_task_from_note(task_id, note_id)
    note = get_note(note_id)
    return render_template('partials/linked_tasks.html', note=note)


@notes_bp.route('/api/tasks-search')
def tasks_search():
    q = request.args.get('q', '')
    if len(q) < 2:
        return ''
    tasks = search_tasks(query=q)[:10]
    return render_template('partials/task_search_dropdown.html', tasks=tasks)


@notes_bp.route('/api/note-titles')
def note_titles():
    return jsonify(get_note_title_map())


@notes_bp.route('/api/graph-data')
def graph_data():
    return jsonify(get_graph_data())
