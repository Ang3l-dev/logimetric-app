from flask import Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='')
from . import routes  # noqa: F401, E402
