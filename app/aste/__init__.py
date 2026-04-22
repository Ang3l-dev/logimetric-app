from flask import Blueprint
aste_bp = Blueprint('aste', __name__, url_prefix='/aste')
from . import routes  # noqa
