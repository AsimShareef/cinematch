from flask import Blueprint, render_template

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def home():
    return render_template('index.html')


@pages_bp.route('/search')
def search():
    return render_template('search_results.html')


@pages_bp.route('/mood')
def mood():
    return render_template('mood.html')


@pages_bp.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    return render_template('movie_detail.html', movie_id=movie_id)


@pages_bp.route('/login')
def login():
    return render_template('auth/login.html')


@pages_bp.route('/register')
def register():
    return render_template('auth/register.html')


@pages_bp.route('/profile')
def profile():
    return render_template('profile.html')
