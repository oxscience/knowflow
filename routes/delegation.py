from flask import Blueprint, render_template, request, jsonify
from models import (
    get_delegated_tasks, mark_delegation_sent, mark_delegation_completed,
    get_email_log, get_task, create_task, create_remote_task, get_remote_task,
    get_received_tasks, update_task, update_remote_sync
)
from services.email_service import (
    send_digest, check_replies, check_incoming_tasks, check_email_to_tasks,
    send_status_update, is_configured, test_connection
)

delegation_bp = Blueprint('delegation', __name__)


@delegation_bp.route('/delegation')
def dashboard():
    tasks = get_delegated_tasks()
    received = get_received_tasks()
    log = get_email_log(limit=20)
    email_ready = is_configured()
    return render_template('delegation.html', tasks=tasks, received=received,
                           log=log, email_ready=email_ready, active='delegation')


@delegation_bp.route('/delegation/send-digest', methods=['POST'])
def send_digest_action():
    if not is_configured():
        return jsonify(error='Email not configured. Add EMAIL_ADDRESS and EMAIL_PASSWORD to .env'), 400

    send_all = request.args.get('all') == '1'
    tasks = get_delegated_tasks(unsent_only=not send_all)

    if not tasks:
        return render_template('partials/digest_result.html',
                               results=[], message='No delegated tasks to send.')

    results = send_digest(tasks)

    # Update DB for successful sends
    for r in results:
        if r['status'] == 'sent':
            mark_delegation_sent(r['task_id'], r.get('message_id'))

    return render_template('partials/digest_result.html', results=results, message=None)


@delegation_bp.route('/delegation/check-replies', methods=['POST'])
def check_replies_action():
    if not is_configured():
        return jsonify(error='Email not configured'), 400

    try:
        replies = check_replies()
    except Exception as e:
        return render_template('partials/replies_result.html',
                               replies=[], error=str(e))

    completed = []
    for reply in replies:
        if reply['completed']:
            task = get_task(reply['task_id'])
            if task and task['status'] != 'done':
                mark_delegation_completed(
                    reply['task_id'],
                    snippet=reply.get('snippet', ''),
                    from_addr=reply.get('from', '')
                )
                completed.append(reply)

    return render_template('partials/replies_result.html',
                           replies=completed, error=None)


@delegation_bp.route('/delegation/sync-inbox', methods=['POST'])
def sync_inbox_action():
    """Check inbox for incoming KnowFlow tasks and status updates."""
    if not is_configured():
        return jsonify(error='Email not configured'), 400

    try:
        incoming = check_incoming_tasks()
    except Exception as e:
        return render_template('partials/sync_result.html',
                               imported=[], updated=[], email_tasks=[],
                               error=str(e))

    imported = []
    updated = []

    for item in incoming:
        if item['type'] == 'task_delegation':
            # Check if we already have this remote task
            existing = get_remote_task(item['remote_id'], item['remote_source'])
            if existing:
                continue  # Already imported, skip

            task = create_remote_task(
                remote_id=item['remote_id'],
                remote_source=item['remote_source'],
                title=item['title'],
                description=item.get('description', ''),
                priority=item.get('priority', 'medium'),
                due_date=item.get('due_date'),
                category_name=item.get('category_name'),
                tags=item.get('tags'),
            )
            imported.append(task)

        elif item['type'] == 'status_update':
            # Find the original task and update its status
            task_id = item['remote_task_id']
            task = get_task(task_id)
            if task and task.get('is_delegated'):
                new_status = item['new_status']
                if new_status in ('todo', 'in_progress', 'done'):
                    update_task(task_id, status=new_status)
                    if new_status == 'done':
                        mark_delegation_completed(task_id,
                                                  snippet=f'Status set to done by {item["sender_email"]}',
                                                  from_addr=item['sender_email'])
                    updated.append({
                        'task_id': task_id,
                        'title': task['title'],
                        'new_status': new_status,
                        'from': item['sender_email'],
                    })

    # Check for email-to-task emails (keyword or forwarded)
    email_tasks = []
    try:
        email_items = check_email_to_tasks()
        for item in email_items:
            task = create_task(
                title=item['title'],
                description=item.get('description', ''),
                tags=['email'],
            )
            email_tasks.append({
                'task': task,
                'sender': item['sender_name'],
                'is_forwarded': item.get('is_forwarded', False),
            })
    except Exception:
        pass  # Don't fail sync if email-to-task fails

    return render_template('partials/sync_result.html',
                           imported=imported, updated=updated,
                           email_tasks=email_tasks, error=None)


@delegation_bp.route('/delegation/send-status-update/<int:task_id>', methods=['POST'])
def send_status_update_action(task_id):
    """Manually send a status update for a received remote task."""
    task = get_task(task_id)
    if not task or not task.get('is_remote'):
        return '', 404

    try:
        send_status_update(task)
        update_remote_sync(task_id)
    except Exception as e:
        return render_template('partials/sync_result.html',
                               imported=[], updated=[], error=str(e))

    return render_template('partials/sync_result.html',
                           imported=[], updated=[{
                               'task_id': task_id,
                               'title': task['title'],
                               'new_status': task['status'],
                               'from': 'you → ' + task['remote_source'],
                           }], error=None)


@delegation_bp.route('/delegation/test-connection', methods=['POST'])
def test_connection_action():
    if not is_configured():
        return render_template('partials/test_result.html',
                               results={'smtp': 'Not configured', 'imap': 'Not configured'})
    results = test_connection()
    return render_template('partials/test_result.html', results=results)
