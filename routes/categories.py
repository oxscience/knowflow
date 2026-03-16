from flask import Blueprint, request, jsonify
from models import get_categories, create_category, delete_category

categories_bp = Blueprint('categories', __name__)


@categories_bp.route('/categories')
def list_categories():
    cats = get_categories()
    return jsonify([dict(c) for c in cats])


@categories_bp.route('/categories', methods=['POST'])
def create():
    data = request.get_json()
    name = data.get('name', '').strip()
    color = data.get('color', '#6b7280')
    if not name:
        return jsonify(error='Name required'), 400
    cat = create_category(name, color)
    return jsonify(dict(cat))


@categories_bp.route('/categories/<int:cat_id>', methods=['DELETE'])
def delete(cat_id):
    delete_category(cat_id)
    return '', 204
