from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any


@dataclass
class TransferRow:
    from_location: str = ''
    to_location: str = ''
    travel_date: date | None = None
    departure_time: time | None = None
    transport: str = ''
    notes: str = ''


@dataclass
class RentalData:
    pickup_location: str = ''
    pickup_date: date | None = None
    pickup_time: time | None = None
    dropoff_location: str = ''
    dropoff_date: date | None = None
    dropoff_time: time | None = None
    vehicle_category: str = ''


@dataclass
class StayRow:
    location: str = ''
    check_in: date | None = None
    check_out: date | None = None


@dataclass
class TravelFormData:
    travel_type: str = 'mista'
    start_date: date | None = None
    end_date: date | None = None
    full_name: str = ''
    employee_id: str = ''
    business_line: str = ''
    cost_center: str = ''
    hiring_location: str = ''
    travel_reason: str = ''
    transfers: list[TransferRow] = field(default_factory=list)
    rental: RentalData = field(default_factory=RentalData)
    stays: list[StayRow] = field(default_factory=list)
    employee_signature_name: str = ''
    employee_signature_date: date | None = None

    @property
    def safe_filename_base(self) -> str:
        name = '_'.join(p for p in self.full_name.replace('/', ' ').split() if p)
        date_part = self.start_date.isoformat() if self.start_date else datetime.now().date().isoformat()
        return f'Trasferta_{name or "SenzaNome"}_{date_part}'


@dataclass
class WeeklyProgramData:
    full_name: str = ''
    start_date: date | None = None
    end_date: date | None = None
    day_locations: list[str] = field(default_factory=lambda: ['', '', '', '', ''])

    @property
    def effective_dates(self) -> list[date]:
        if self.start_date:
            return [self.start_date + timedelta(days=i) for i in range(5)]
        return []

    @property
    def safe_filename_base(self) -> str:
        name = '_'.join(p for p in self.full_name.replace('/', ' ').split() if p)
        date_part = self.start_date.isoformat() if self.start_date else datetime.now().date().isoformat()
        return f'ProgrammaSettimanale_{name or "SenzaNome"}_{date_part}'


# ── Parser ────────────────────────────────────────────────────────────────────
def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def parse_time(value: str | None) -> time | None:
    if not value:
        return None
    return datetime.strptime(value, '%H:%M').time()


def from_form(form: dict[str, Any]) -> TravelFormData:
    transfers: list[TransferRow] = []
    i = 0
    while True:
        p = f'transfers-{i}-'
        if f'{p}from_location' not in form:
            break
        row = TransferRow(
            from_location=(form.get(f'{p}from_location') or '').strip(),
            to_location=(form.get(f'{p}to_location') or '').strip(),
            travel_date=parse_date(form.get(f'{p}travel_date')),
            departure_time=parse_time(form.get(f'{p}departure_time')),
            transport=(form.get(f'{p}transport') or '').strip(),
            notes=(form.get(f'{p}notes') or '').strip(),
        )
        if any([row.from_location, row.to_location, row.travel_date,
                row.departure_time, row.transport, row.notes]):
            transfers.append(row)
        i += 1

    stays: list[StayRow] = []
    i = 0
    while True:
        p = f'stays-{i}-'
        if f'{p}location' not in form:
            break
        row = StayRow(
            location=(form.get(f'{p}location') or '').strip(),
            check_in=parse_date(form.get(f'{p}check_in')),
            check_out=parse_date(form.get(f'{p}check_out')),
        )
        if any([row.location, row.check_in, row.check_out]):
            stays.append(row)
        i += 1

    return TravelFormData(
        travel_type=(form.get('travel_type') or 'mista').strip(),
        start_date=parse_date(form.get('start_date')),
        end_date=parse_date(form.get('end_date')),
        full_name=(form.get('full_name') or '').strip(),
        employee_id=(form.get('employee_id') or '').strip(),
        business_line=(form.get('business_line') or '').strip(),
        cost_center=(form.get('cost_center') or '').strip(),
        hiring_location=(form.get('hiring_location') or '').strip(),
        travel_reason=(form.get('travel_reason') or '').strip(),
        transfers=transfers,
        rental=RentalData(
            pickup_location=(form.get('pickup_location') or '').strip(),
            pickup_date=parse_date(form.get('pickup_date')),
            pickup_time=parse_time(form.get('pickup_time')),
            dropoff_location=(form.get('dropoff_location') or '').strip(),
            dropoff_date=parse_date(form.get('dropoff_date')),
            dropoff_time=parse_time(form.get('dropoff_time')),
            vehicle_category=(form.get('vehicle_category') or '').strip(),
        ),
        stays=stays,
        employee_signature_name=(form.get('employee_signature_name') or '').strip(),
        employee_signature_date=parse_date(form.get('employee_signature_date')),
    )


def weekly_from_form(form: dict[str, Any]) -> WeeklyProgramData:
    return WeeklyProgramData(
        full_name=(form.get('full_name') or '').strip(),
        start_date=parse_date(form.get('start_date')),
        end_date=parse_date(form.get('end_date')),
        day_locations=[(form.get(f'day_location_{i}') or '').strip() for i in range(1, 6)],
    )
