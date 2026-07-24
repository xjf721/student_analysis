from flask import jsonify, redirect, request, session, url_for


PUBLIC_ENDPOINTS = {'auth.login', 'static'}


def install_request_guards(app):
    @app.before_request
    def require_authentication():
        if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if session.get('authenticated'):
            return None
        if request.path.startswith('/api/'):
            return jsonify({'error': 'authentication_required'}), 401
        return redirect(url_for('auth.login', next=request.full_path))
