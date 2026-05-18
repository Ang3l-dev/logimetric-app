from flask import Blueprint
dispensa_bp = Blueprint('dispensa', __name__, url_prefix='/dispensa')
from . import routes  # noqa
