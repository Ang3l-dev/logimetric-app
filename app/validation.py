from __future__ import annotations
from .services.data_models import TravelFormData, WeeklyProgramData


def validate_form(data: TravelFormData) -> list[str]:
    errors: list[str] = []
    if not data.start_date:
        errors.append('La data iniziale è obbligatoria.')
    if not data.end_date:
        errors.append('La data finale è obbligatoria.')
    if data.start_date and data.end_date and data.start_date > data.end_date:
        errors.append('La data iniziale non può essere successiva alla data finale.')
    required = {
        'Cognome e nome': data.full_name, 'Matricola': data.employee_id,
        'Linea di business': data.business_line, 'Centro di costo': data.cost_center,
        'Sede di assunzione': data.hiring_location, 'Motivo del viaggio': data.travel_reason,
    }
    for label, val in required.items():
        if not val:
            errors.append(f'Il campo "{label}" è obbligatorio.')
    if not data.transfers:
        errors.append('Inserisci almeno un trasferimento.')
    for i, tr in enumerate(data.transfers, 1):
        if not tr.from_location or not tr.to_location:
            errors.append(f'Trasferimento {i}: partenza e arrivo obbligatori.')
        if not tr.travel_date:
            errors.append(f'Trasferimento {i}: la data è obbligatoria.')
    for i, st in enumerate(data.stays, 1):
        if st.check_in and st.check_out and st.check_in > st.check_out:
            errors.append(f'Pernottamento {i}: la data IN non può essere successiva alla data OUT.')
    return errors


def validate_weekly(data: WeeklyProgramData) -> list[str]:
    errors: list[str] = []
    if not data.full_name:
        errors.append('Il nome è obbligatorio.')
    if not data.start_date:
        errors.append('La data iniziale è obbligatoria.')
    if not data.end_date:
        errors.append('La data finale è obbligatoria.')
    if data.start_date and data.end_date and data.start_date > data.end_date:
        errors.append('La data iniziale non può essere successiva alla data finale.')
    if data.start_date and data.end_date:
        diff = (data.end_date - data.start_date).days
        if diff != 4:
            errors.append('Il programma settimanale richiede esattamente 5 giorni: '
                          'la data finale deve essere 4 giorni dopo la data iniziale.')
    if not any(data.day_locations):
        errors.append('Inserisci almeno una sede giornaliera.')
    return errors
