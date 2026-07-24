from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for
from models import ClassInfo


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


def get_active_class_id() -> int:
    return g.active_class.id


def require_active_class(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        class_id = session.get('active_class_id')
        active = ClassInfo.query.filter_by(id=class_id, status='active').first() if class_id else None
        if active is None:
            session.pop('active_class_id', None)
            if request.path.startswith('/api/'):
                return jsonify({'error': 'active_class_required'}), 409
            return redirect(url_for('classes.index'))
        g.active_class = active
        return view(*args, **kwargs)
    return wrapped


def install_template_context(app):
    @app.context_processor
    def class_navigation_context():
        if not session.get('authenticated'):
            return {}
        class_id = session.get('active_class_id')
        return {
            'active_class': ClassInfo.query.filter_by(id=class_id, status='active').first(),
            'active_classes': ClassInfo.query.filter_by(status='active').order_by(ClassInfo.class_name).all(),
        }
