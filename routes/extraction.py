from flask import Blueprint, render_template, request, jsonify
from models import (
    create_task, link_task_to_note, set_task_tags,
    get_or_create_tag, get_or_create_contact, get_note, get_task_tags
)
from services.extraction_service import extract_from_note, is_configured

extraction_bp = Blueprint('extraction', __name__)


@extraction_bp.route('/api/extract/<int:note_id>', methods=['POST'])
def extract(note_id):
    if not is_configured():
        return render_template('partials/ai_suggestions.html',
                               suggestions=None, note_id=note_id,
                               llm_configured=False)

    note = get_note(note_id)
    if not note:
        return '', 404

    content = note.get('content', '')
    suggestions = extract_from_note(content, note_id=note_id)

    return render_template('partials/ai_suggestions.html',
                           suggestions=suggestions, note_id=note_id,
                           llm_configured=True)


@extraction_bp.route('/api/extract/accept-task/<int:note_id>', methods=['POST'])
def accept_task(note_id):
    title = request.form.get('title', '').strip()
    priority = request.form.get('priority', 'medium')
    due_date = request.form.get('due_date') or None
    assignee_name = request.form.get('assignee_name', '').strip()
    assignee_email = request.form.get('assignee_email', '').strip()
    tags_str = request.form.get('tags', '')
    tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []

    if not title:
        return '', 400

    is_delegated = bool(assignee_email)
    if is_delegated and assignee_name:
        get_or_create_contact(assignee_name, assignee_email)

    task = create_task(
        title=title,
        priority=priority,
        due_date=due_date,
        is_delegated=is_delegated,
        assignee_name=assignee_name,
        assignee_email=assignee_email,
        tags=tags,
    )
    link_task_to_note(task['id'], note_id)

    note = get_note(note_id)
    return render_template('partials/linked_tasks.html', note=note)


@extraction_bp.route('/api/extract/accept-contact', methods=['POST'])
def accept_contact():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    if not name:
        return '', 400
    get_or_create_contact(name, email or '')
    return '<div class="suggestion-accepted">Contact added</div>'


@extraction_bp.route('/api/extract/accept-tag/<int:note_id>', methods=['POST'])
def accept_tag(note_id):
    tag_name = request.form.get('tag_name', '').strip()
    if not tag_name:
        return '', 400
    get_or_create_tag(tag_name)

    apply_to_tasks = request.form.get('apply_to_tasks') == '1'
    if apply_to_tasks:
        note = get_note(note_id)
        if note and note.get('linked_tasks'):
            for linked in note['linked_tasks']:
                existing = [t['name'] for t in get_task_tags(linked['id'])]
                if tag_name not in existing:
                    set_task_tags(linked['id'], existing + [tag_name])

    return '<div class="suggestion-accepted">Tag added</div>'


@extraction_bp.route('/api/extract/accept-link/<int:note_id>', methods=['POST'])
def accept_link(note_id):
    target_title = request.form.get('target_title', '')
    return jsonify({'wiki_link': f'[[{target_title}]]'})
