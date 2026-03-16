from flask import Blueprint, render_template, request
from models import search_tasks

api_bp = Blueprint('api', __name__)


@api_bp.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    status = request.args.get('status') or None
    priority = request.args.get('priority') or None
    category_id = request.args.get('category_id') or None
    delegated = request.args.get('delegated')

    if delegated is not None and delegated != '':
        delegated = delegated == '1'
    else:
        delegated = None

    tasks = search_tasks(
        query=q, status=status, priority=priority,
        category_id=category_id, delegated=delegated
    )
    return render_template('partials/search_results.html', tasks=tasks, query=q)
