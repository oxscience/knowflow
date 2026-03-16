from flask import Blueprint, render_template, request
from models import get_contacts, get_or_create_contact, delete_contact, get_categories, create_category, delete_category

team_bp = Blueprint('team', __name__)


@team_bp.route('/team')
def index():
    contacts = get_contacts()
    categories = get_categories()
    return render_template('team.html', contacts=contacts, categories=categories, active='team')


@team_bp.route('/team/contacts', methods=['POST'])
def add_contact():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    if email:
        get_or_create_contact(name or email, email)
    contacts = get_contacts()
    return render_template('partials/contact_list.html', contacts=contacts)


@team_bp.route('/team/contacts/<int:contact_id>', methods=['DELETE'])
def remove_contact(contact_id):
    delete_contact(contact_id)
    contacts = get_contacts()
    return render_template('partials/contact_list.html', contacts=contacts)


@team_bp.route('/team/categories', methods=['POST'])
def add_category():
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#6b7280')
    if name:
        create_category(name, color)
    categories = get_categories()
    return render_template('partials/category_list.html', categories=categories)


@team_bp.route('/team/categories/<int:cat_id>', methods=['DELETE'])
def remove_category(cat_id):
    delete_category(cat_id)
    categories = get_categories()
    return render_template('partials/category_list.html', categories=categories)
