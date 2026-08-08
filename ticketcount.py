#!/usr/bin/env python3
import datetime
import os
import socket
import sys

from sqlalchemy import text


VALID_SCACS = {'OSLM', 'FELA', 'NEVO'}


def parse_time_minutes(value):
    if value in (None, ''):
        return None
    cleaned = str(value).strip()
    for fmt in ('%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M%p'):
        try:
            parsed = datetime.datetime.strptime(cleaned.upper(), fmt)
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            continue
    digits = ''.join(ch for ch in cleaned if ch.isdigit())
    if len(digits) in (3, 4):
        hour = int(digits[:-2])
        minute = int(digits[-2:])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour * 60 + minute
    return None


def service_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def terminal_key(row):
    return (row.get('Path') or row.get('Source') or row.get('Company') or '').strip().lower()


def is_gate_move(row):
    gate_type = (row.get('Type') or '').lower()
    return any(token in gate_type for token in ['in', 'out', 'dray'])


def setup_agent_imports(scac):
    host_name = socket.gethostname()
    agents_path = os.path.dirname(os.path.abspath(__file__))
    if agents_path not in sys.path:
        sys.path.append(agents_path)
    from utils import getpaths

    sys_path = getpaths(host_name, 'system')
    if sys_path not in sys.path:
        sys.path.append(sys_path)

    os.environ['SCAC'] = scac
    os.environ['PURPOSE'] = 'script'
    os.environ['MACHINE'] = host_name
    os.environ['TUNNEL'] = 'remote'


def ensure_port_trip_column(db):
    result = db.session.execute(text("SHOW COLUMNS FROM interchange LIKE 'PortTrip'")).fetchone()
    if not result:
        db.session.execute(text("ALTER TABLE interchange ADD COLUMN PortTrip INT DEFAULT NULL"))
        db.session.commit()


def fetch_year_rows(db, year):
    start_dt = datetime.datetime(year, 1, 1, 0, 0, 0)
    end_dt = datetime.datetime(year, 12, 31, 23, 59, 59)
    return db.session.execute(text("""
        SELECT id, Container, TruckNumber, Driver, Date, Time, Type, Source, Path, Company
        FROM interchange
        WHERE Date >= :start_dt AND Date <= :end_dt
        ORDER BY Date ASC, TruckNumber ASC, Driver ASC, id ASC
    """), {'start_dt': start_dt, 'end_dt': end_dt}).mappings().all()


def rebaseline_ticket_counts(db, year):
    rows = fetch_year_rows(db, year)
    if not rows:
        return {'rows_reviewed': 0, 'rows_updated': 0, 'port_trips': 0}

    db.session.execute(text("""
        UPDATE interchange
        SET PortTrip = NULL
        WHERE Date >= :start_dt AND Date <= :end_dt
    """), {
        'start_dt': datetime.datetime(year, 1, 1, 0, 0, 0),
        'end_dt': datetime.datetime(year, 12, 31, 23, 59, 59),
    })

    groups = {}
    for row in rows:
        if not is_gate_move(row):
            continue
        row_date = service_date(row.get('Date'))
        if not row_date:
            continue
        key = (
            row_date,
            (row.get('TruckNumber') or '').strip().lower(),
            (row.get('Driver') or '').strip().lower(),
            terminal_key(row),
        )
        groups.setdefault(key, []).append(row)

    trip_groups = []
    for key in groups:
        group_rows = sorted(
            groups[key],
            key=lambda item: (
                parse_time_minutes(item.get('Time')) if parse_time_minutes(item.get('Time')) is not None else 99999,
                item.get('id'),
            ),
        )
        current_trip_start = None
        current_rows = []
        for row in group_rows:
            row_time = parse_time_minutes(row.get('Time'))
            if not current_rows:
                current_rows = [row]
                current_trip_start = row_time
            elif row_time is not None and current_trip_start is not None and abs(row_time - current_trip_start) > 180:
                trip_groups.append(current_rows)
                current_rows = [row]
                current_trip_start = row_time
            else:
                current_rows.append(row)
        if current_rows:
            trip_groups.append(current_rows)

    trip_groups.sort(key=lambda group: (
        service_date(group[0].get('Date')),
        parse_time_minutes(group[0].get('Time')) if parse_time_minutes(group[0].get('Time')) is not None else 99999,
        group[0].get('id'),
    ))
    updates = []
    trip_number = 1
    for trip_rows in trip_groups:
        for row in trip_rows:
            updates.append({'id': row.get('id'), 'port_trip': trip_number})
        trip_number += 1

    for item in updates:
        db.session.execute(text("""
            UPDATE interchange
            SET PortTrip = :port_trip
            WHERE id = :id
        """), item)
    db.session.commit()
    return {'rows_reviewed': len(rows), 'rows_updated': len(updates), 'port_trips': trip_number - 1}


def main():
    if len(sys.argv) != 3:
        print('Usage: ticketcount <scac> <year>')
        print('Example: ticketcount oslm 2026')
        return 2
    scac = sys.argv[1].upper()
    if scac not in VALID_SCACS:
        print('SCAC must be one of: ' + ', '.join(sorted(VALID_SCACS)))
        return 2
    try:
        year = int(sys.argv[2])
    except ValueError:
        print('Year must be a four-digit integer.')
        return 2
    if year < 2000 or year > 2100:
        print('Year must be between 2000 and 2100.')
        return 2

    setup_agent_imports(scac)
    from remote_db_connect import db
    try:
        from remote_db_connect import tunnel
    except ImportError:
        tunnel = None

    ensure_port_trip_column(db)
    result = rebaseline_ticket_counts(db, year)
    print(f"{scac} {year}: reviewed {result['rows_reviewed']} interchange rows")
    print(f"{scac} {year}: updated {result['rows_updated']} gate rows")
    print(f"{scac} {year}: assigned {result['port_trips']} port trip numbers")
    if tunnel:
        tunnel.stop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
