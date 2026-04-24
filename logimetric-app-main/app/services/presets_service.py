from __future__ import annotations
import json
from flask_login import current_user
from .. import db
from ..models import Preset


def list_presets(preset_type: str | None = None) -> list[dict]:
    q = Preset.query.filter_by(user_id=current_user.id)
    if preset_type:
        q = q.filter_by(preset_type=preset_type)
    rows = q.order_by(Preset.name).all()
    return [{'id': p.id, 'name': p.name, 'preset_type': p.preset_type,
             'payload': json.loads(p.payload)} for p in rows]


def get_preset(preset_id: int) -> dict | None:
    p = Preset.query.filter_by(id=preset_id, user_id=current_user.id).first()
    if not p:
        return None
    return {'id': p.id, 'name': p.name, 'preset_type': p.preset_type,
            'payload': json.loads(p.payload)}


def upsert_preset(name: str, payload: dict, preset_type: str = 'travel',
                  preset_id: int | None = None) -> int:
    serialized = json.dumps(payload, ensure_ascii=False)
    if preset_id:
        p = Preset.query.filter_by(id=preset_id, user_id=current_user.id).first()
        if p:
            p.name = name
            p.preset_type = preset_type
            p.payload = serialized
            db.session.commit()
            return p.id
    p = Preset(user_id=current_user.id, name=name,
               preset_type=preset_type, payload=serialized)
    db.session.add(p)
    db.session.commit()
    return p.id


def delete_preset(preset_id: int) -> None:
    p = Preset.query.filter_by(id=preset_id, user_id=current_user.id).first()
    if p:
        db.session.delete(p)
        db.session.commit()
