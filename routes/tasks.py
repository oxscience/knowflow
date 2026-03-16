from flask import Blueprint, render_template, request, jsonify

from models import (
    create_task, get_task, update_task, delete_task,
    update_task_status, get_categories, get_tags,
    get_contacts, get_or_create_contact, update_remote_sync
)
from services.email_service import send_status_update, is_configured as email_configured

tasks_bp = Blueprint('tasks', __name__)


def _notify_remote_status(task):
    """If a remote task changed status, send update back to sender."""
    if task and task.get('is_remote') and task.get('remote_source') and email_configured():
        try:
            send_status_update(task)
            update_remote_sync(task['id'])
        except Exception:
            pass  # Don't break the UI if email fails


@tasks_bp.route('/tasks', methods=['POST'])
def create():
    title = request.form.get('title', '').strip()
    if not title:
        return '', 400

    priority = request.form.get('priority', 'medium')
    category_id = request.form.get('category_id') or None

    task = create_task(title=title, priority=priority, category_id=category_id)
    return render_template('partials/task_card.html', task=task)


@tasks_bp.route('/tasks/<int:task_id>')
def detail(task_id):
    task = get_task(task_id)
    if not task:
        return '', 404
    categories = get_categories()
    contacts = get_contacts()
    return render_template('partials/task_detail.html', task=task,
                           categories=categories, contacts=contacts)


@tasks_bp.route('/tasks/<int:task_id>', methods=['PUT'])
def update(task_id):
    data = request.form
    tags_str = data.get('tags', '')
    tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []

    is_delegated = data.get('is_delegated') == 'on'
    assignee_name = data.get('assignee_name', '').strip()
    assignee_email = data.get('assignee_email', '').strip()

    # Auto-save contact when delegating
    if is_delegated and assignee_email:
        get_or_create_contact(assignee_name, assignee_email)

    old_task = get_task(task_id)
    old_status = old_task['status'] if old_task else None

    task = update_task(
        task_id,
        title=data.get('title'),
        description=data.get('description'),
        priority=data.get('priority'),
        category_id=data.get('category_id') or None,
        is_delegated=is_delegated,
        assignee_name=assignee_name,
        assignee_email=assignee_email,
        due_date=data.get('due_date') or None,
        tags=tags,
    )
    if not task:
        return '', 404

    # If remote task status changed, notify the sender
    if task.get('is_remote') and task['status'] != old_status:
        _notify_remote_status(task)

    # Return the right partial depending on which view the user is on
    current_url = request.headers.get('HX-Current-URL', '')
    if '/list' in current_url or '/delegation' in current_url:
        return render_template('partials/task_row.html', task=task)
    return render_template('partials/task_card.html', task=task)


@tasks_bp.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete(task_id):
    if delete_task(task_id):
        return ''
    return '', 404


@tasks_bp.route('/tasks/<int:task_id>/status', methods=['PATCH'])
def change_status(task_id):
    data = request.get_json()
    new_status = data.get('status')
    new_position = data.get('position', 0)

    if new_status not in ('todo', 'in_progress', 'done'):
        return jsonify(error='Invalid status'), 400

    old_task = get_task(task_id)
    old_status = old_task['status'] if old_task else None

    task = update_task_status(task_id, new_status, new_position)
    if not task:
        return '', 404

    # If remote task status changed via drag-and-drop, notify the sender
    if task.get('is_remote') and new_status != old_status:
        _notify_remote_status(task)

    return jsonify(ok=True)
