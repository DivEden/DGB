# pages/resizer.py
from flask import Blueprint, render_template

resizer_bp = Blueprint("resizer", __name__)

@resizer_bp.route("/")
def view():
    return render_template(
        'resizer.html',
        current_page='resizer'
    )
