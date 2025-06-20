from functools import wraps
from flask import current_app, request
from identity.flask import Auth

def optional_auth(f=None, scopes=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_app.config.get('AUTH_ENABLED', True):
                auth = current_app.auth_instance
                if scopes:
                    return auth.login_required(scopes=scopes)(f)(*args, **kwargs)
                return auth.login_required(f)(*args, **kwargs)
            
            # Only use mock context when auth is explicitly disabled
            mock_context = {
                'user': {'name': 'Test User'},
                'access_token': 'mock_token'
            }
            return f(*args, context=mock_context, **kwargs)
        return wrapped
    return decorator if f is None else decorator(f)