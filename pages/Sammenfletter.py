# pages/Sammenfletter.py
from flask import Blueprint, render_template

sammenfletter_bp = Blueprint("sammenfletter", __name__)

@sammenfletter_bp.route("/")
def view():
    return render_template(
        'sammenfletter.html',
        current_page='sammenfletter'
    )
