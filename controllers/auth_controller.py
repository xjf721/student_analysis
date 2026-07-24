from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from extensions import limiter
from services.auth_service import authenticate, credentials_configured


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per 15 minutes', methods=['POST'])
def login():
    if not credentials_configured():
        return render_template('auth/login.html', config_error=True), 503
    if request.method == 'GET':
        return render_template('auth/login.html', config_error=False)
    if not authenticate(request.form.get('username', ''), request.form.get('password', '')):
        return render_template(
            'auth/login.html', error='用户名或密码错误', config_error=False
        ), 401

    session.clear()
    session['authenticated'] = True
    session['admin_username'] = current_app.config['ADMIN_USERNAME']
    return redirect('/classes')


@auth_bp.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
