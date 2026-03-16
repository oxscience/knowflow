from datetime import date, timedelta
from flask import Blueprint, render_template, request
from models import get_all_tasks_grouped, search_tasks

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
def index():
    return kanban()


@views_bp.route('/kanban')
def kanban():
    tasks = get_all_tasks_grouped()
    delegate_name = request.args.get('delegate_name', '')
    delegate_email = request.args.get('delegate_email', '')
    soon_date = (date.today() + timedelta(days=7)).isoformat()
    return render_template('kanban.html', tasks=tasks, active='kanban',
                           delegate_name=delegate_name, delegate_email=delegate_email,
                           soon_date=soon_date)


@views_bp.route('/list')
def list_view():
    status = request.args.get('status')
    priority = request.args.get('priority')
    category_id = request.args.get('category_id')
    delegated = request.args.get('delegated')

    if delegated is not None:
        delegated = delegated == '1'

    tasks = search_tasks(
        status=status or None,
        priority=priority or None,
        category_id=category_id or None,
        delegated=delegated
    )
    return render_template('list.html', tasks=tasks, active='list',
                           filter_status=status or '',
                           filter_priority=priority or '',
                           filter_category=category_id or '',
                           filter_delegated=request.args.get('delegated', ''))
