import os
import json
import calendar
import re
import socket
import sys
import time
from datetime import date, datetime
from urllib.parse import quote_plus

from sqlalchemy import text

from utils import getpaths, hasinput

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.path.dirname(__file__), ".ms-playwright"))

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError as exc:
    raise SystemExit(
        "The Playwright Python package is not installed. Install it in the "
        "flaskenv venv with: pip install playwright && playwright install chromium"
    ) from exc


try:
    scac = sys.argv[1]
    nt = "remote"
except Exception:
    scac = "fela"
    nt = "remote"

scac = scac.upper()

if scac not in ("OSLM", "FELA", "NEVO"):
    print("The argument must be FELA or OSLM or NEVO")
    quit()

print(f"Running III_New_Order_Booking_Review for {scac} in tunnel mode: {nt}")

host_name = socket.gethostname()
print("Host Name:", host_name)
sys_path = getpaths(host_name, "system")
sys.path.append(sys_path)

os.environ["SCAC"] = scac
os.environ["PURPOSE"] = "script"
os.environ["MACHINE"] = host_name
os.environ["TUNNEL"] = nt

from remote_db_connect import db

if nt == "remote":
    from remote_db_connect import tunnel

from models8 import Orders


RUN_AT = datetime.now()
TODAY = RUN_AT.date()
REVIEW_STATUSES = ("new_orders", "upcoming_deliveries", "port_today", "drop_pick")
REVIEW_STATUS_LABELS = {
    "new_orders": "New Orders",
    "upcoming_deliveries": "Upcoming Deliveries",
    "port_today": "Port Today",
    "drop_pick": "Drop-Pick",
}
ON_CALL_IMPORT_LABEL = "On Call imports without ECCES hold"
BOOKING_URL = "https://www.portsamerica.com/resources/inquiries?location=SGT_BAL&option=bookingInquiry&numbers={booking}"
CONTAINER_URL = "https://www.portsamerica.com/resources/inquiries?location=SGT_BAL&option=containerByContainer&numbers={container}"
BOL_URL = "https://www.portsamerica.com/resources/inquiries?location=SGT_BAL&option=containerByBol&numbers={bol}"
ECCES_LOOKUP_URL = "https://ces.myecw.com/containerLookup"
ECCES_API_URL = "https://ces.myecw.com/api/containerDetails?containerNumber={container}&billOfLading={bol}"
PORTS_AMERICA_SCHEDULE_URL = "https://www.portsamerica.com/our-locations/schedules/baltimore-md"
SCHEDULE_UNLOAD_CACHE = {}


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def strip_booking(value):
    value = clean_text(value)
    if "-" in value:
        value = value.split("-", 1)[0]
    return value


def parse_port_date(value):
    value = clean_text(value)
    if not value or value.upper() == "NOF":
        return None

    value = value.split(" ", 1)[0]
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def combined_date_time(data, date_key, time_key):
    date_value = clean_text(data.get(date_key))
    time_value = clean_text(data.get(time_key))
    if date_value and time_value:
        return f"{date_value} {time_value}"
    return date_value or time_value


def normalize_vessel_name(value):
    return re.sub(r"[^A-Z0-9]+", " ", clean_text(value).upper()).strip()


def add_months(year, month, delta):
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def format_unload_note(unload_dates):
    unload_dates = sorted(set(unload_dates))
    if not unload_dates:
        return ""
    if len(unload_dates) == 1:
        return f"Unloads {unload_dates[0].strftime('%B')} {unload_dates[0].day}"

    first = unload_dates[0]
    last = unload_dates[-1]
    if first.year == last.year and first.month == last.month:
        return f"Unloads {first.strftime('%B')} {first.day}-{last.day}"
    return f"Unloads {first.strftime('%B')} {first.day}-{last.strftime('%B')} {last.day}"


def parse_ports_america_calendar_dates(body_text, vessel_name):
    target = normalize_vessel_name(vessel_name)
    if not target:
        return []

    lines = [clean_text(line) for line in body_text.splitlines()]
    month_ix = None
    base_year = None
    base_month = None
    for ix, line in enumerate(lines):
        match = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", line)
        if match and match.group(1) in calendar.month_name:
            month_ix = ix
            base_year = int(match.group(2))
            base_month = list(calendar.month_name).index(match.group(1))
            break
    if month_ix is None:
        return []

    current_day = None
    previous_day = None
    month_delta = -1
    found_current_month_start = False
    matches = []

    for line in lines[month_ix + 1:]:
        if line == "Legend":
            break
        if re.fullmatch(r"\d{1,2}", line):
            day = int(line)
            if not found_current_month_start and day == 1:
                found_current_month_start = True
                month_delta = 0
            elif found_current_month_start and previous_day and day < previous_day:
                month_delta += 1
            current_day = day
            previous_day = day
            continue
        if current_day is None:
            continue
        if target and target in normalize_vessel_name(line):
            year, month = add_months(base_year, base_month, month_delta)
            try:
                matches.append(date(year, month, current_day))
            except ValueError:
                pass
    return sorted(set(matches))


def get_ports_america_unload_dates(page, vessel_name):
    cache_key = normalize_vessel_name(vessel_name)
    if cache_key in SCHEDULE_UNLOAD_CACHE:
        return SCHEDULE_UNLOAD_CACHE[cache_key]
    print(f"Checking Ports America calendar for vessel {vessel_name}")
    page.goto(PORTS_AMERICA_SCHEDULE_URL, wait_until="networkidle", timeout=60000)
    try:
        page.get_by_role("button", name="Agree").click(timeout=2000)
        page.wait_for_timeout(500)
    except PlaywrightError:
        pass
    body_text = page.locator("body").inner_text(timeout=10000)
    dates = parse_ports_america_calendar_dates(body_text, vessel_name)
    SCHEDULE_UNLOAD_CACHE[cache_key] = dates
    return dates


def append_kanban_note_once(order, note):
    note = clean_text(note)
    if not note:
        return False

    row = db.session.execute(
        text("SELECT Notes FROM dispatch_kanban_state WHERE OrderId = :order_id"),
        {"order_id": order.id},
    ).mappings().first()
    existing_notes = clean_text(row.get("Notes")) if row else ""
    if note.lower() in existing_notes.lower():
        return False

    updated_notes = f"{existing_notes}\n{note}".strip() if existing_notes else note
    now = datetime.utcnow()
    if row:
        db.session.execute(
            text("""
                UPDATE dispatch_kanban_state
                SET Notes = :notes, UpdatedAt = :updated_at
                WHERE OrderId = :order_id
            """),
            {"order_id": order.id, "notes": updated_notes, "updated_at": now},
        )
    else:
        db.session.execute(
            text("""
                INSERT INTO dispatch_kanban_state
                    (OrderId, WorkflowStatus, Notes, CreatedAt, UpdatedAt)
                VALUES
                    (:order_id, :workflow_status, :notes, :created_at, :updated_at)
            """),
            {
                "order_id": order.id,
                "workflow_status": clean_text(order.DisStatus) or "new_orders",
                "notes": updated_notes,
                "created_at": now,
                "updated_at": now,
            },
        )
    db.session.commit()
    return True


def merge_values(primary, secondary, keys):
    for key in keys:
        value = clean_text(secondary.get(key))
        if value:
            primary[key] = value
    return primary


def date_changed(old_value, new_value):
    if isinstance(old_value, datetime):
        old_value = old_value.date()
    return old_value != new_value


def launch_browser():
    playwright = sync_playwright().start()
    headless = os.environ.get("BOOKING_REVIEW_HEADLESS", "1").lower() in ("1", "true", "yes")
    browser = playwright.chromium.launch(
        headless=headless,
        chromium_sandbox=False,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-seccomp-filter-sandbox"],
    )
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    return playwright, browser, page


def cell_texts(table_locator):
    rows = table_locator.locator("tbody tr")
    if rows.count() == 0:
        return []
    cells = rows.first.locator("td")
    return [clean_text(cells.nth(ix).inner_text(timeout=2000)) for ix in range(cells.count())]


def table_row_dict(table_locator):
    headers = []
    header_cells = table_locator.locator("thead th")
    for ix in range(header_cells.count()):
        headers.append(clean_text(header_cells.nth(ix).inner_text(timeout=2000)))

    values = cell_texts(table_locator)
    return {header: values[ix] if ix < len(values) else "" for ix, header in enumerate(headers)}


def legacy_row_cells(page, table_index, cell_count):
    table_xpath = (
        f"/html/body/div[5]/div/div/div[2]/main/div[1]/section/div/div[2]/div/div[4]/"
        f"div/div[3]/div/div/table/tbody/tr[2]/td/div[{table_index}]/div[2]/div/table/tbody/tr"
    )
    row = page.locator(f"xpath={table_xpath}").first
    row.wait_for(state="attached", timeout=10000)
    return [
        clean_text(row.locator(f"xpath=./td[{ix}]").inner_text(timeout=2000))
        for ix in range(1, cell_count + 1)
    ]


def get_booking_details(page, booking):
    url = BOOKING_URL.format(booking=booking)
    print(f"Getting booking inquiry data for {booking}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    booking_table = page.locator("#inquiries-booking-table")
    booking_table.wait_for(state="attached", timeout=20000)

    try:
        expand_button = booking_table.get_by_role("button", name=re.compile(r"^Expand$", re.I)).first
        if expand_button.is_visible(timeout=2000):
            expand_button.click()
            page.wait_for_timeout(1000)
    except PlaywrightError:
        pass

    try:
        vessel_table = page.locator("table[id^='inquiries-booking-vessel-info-table']").first
        vessel_table.wait_for(state="attached", timeout=5000)
        vessel_data = table_row_dict(vessel_table)
    except PlaywrightTimeoutError:
        vessel_cells = legacy_row_cells(page, 1, 11)
        vessel_data = {
            "SSCO": vessel_cells[0] if len(vessel_cells) > 0 else "",
            "Vessel Name": vessel_cells[1] if len(vessel_cells) > 1 else "",
            "Voyage#": vessel_cells[2] if len(vessel_cells) > 2 else "",
            "Empty Start": vessel_cells[3] if len(vessel_cells) > 3 else "",
            "General Begin Receive": vessel_cells[4] if len(vessel_cells) > 4 else "",
            "Reefer Begin Receive": vessel_cells[5] if len(vessel_cells) > 5 else "",
            "Hazardous Begin Receive": vessel_cells[6] if len(vessel_cells) > 6 else "",
            "General Cutoff": vessel_cells[7] if len(vessel_cells) > 7 else "",
            "Reefer Cutoff": vessel_cells[8] if len(vessel_cells) > 8 else "",
            "Hazardous Cutoff": vessel_cells[9] if len(vessel_cells) > 9 else "",
            "Loading At": vessel_cells[10] if len(vessel_cells) > 10 else "",
        }

    try:
        detail_table = page.locator("table[id^='inquiries-booking-info-table']").first
        detail_table.wait_for(state="attached", timeout=5000)
        detail_data = table_row_dict(detail_table)
    except PlaywrightTimeoutError:
        detail_cells = legacy_row_cells(page, 2, 6)
        detail_data = {
            "Length": detail_cells[0] if len(detail_cells) > 0 else "",
            "Type": detail_cells[1] if len(detail_cells) > 1 else "",
            "Height": detail_cells[2] if len(detail_cells) > 2 else "",
            "Total": detail_cells[3] if len(detail_cells) > 3 else "",
            "#Received": detail_cells[4] if len(detail_cells) > 4 else "",
            "#Delivered": detail_cells[5] if len(detail_cells) > 5 else "",
        }

    data = {
        "shipline": vessel_data.get("SSCO", ""),
        "ship": vessel_data.get("Vessel Name", ""),
        "voyage": vessel_data.get("Voyage#", ""),
        "empty_start": vessel_data.get("Empty Start", ""),
        "general_erd": vessel_data.get("General Begin Receive", ""),
        "reefer_erd": vessel_data.get("Reefer Begin Receive", ""),
        "haz_erd": vessel_data.get("Hazardous Begin Receive", ""),
        "general_cutoff": vessel_data.get("General Cutoff", ""),
        "reefer_cutoff": vessel_data.get("Reefer Cutoff", ""),
        "haz_cutoff": vessel_data.get("Hazardous Cutoff", ""),
        "loading_at": vessel_data.get("Loading At", ""),
        "length": detail_data.get("Length", ""),
        "type": detail_data.get("Type", ""),
        "height": detail_data.get("Height", ""),
        "total": detail_data.get("Total", ""),
        "received": detail_data.get("#Received", ""),
        "delivered": detail_data.get("#Delivered", ""),
    }

    data["erd_date"] = parse_port_date(data["general_erd"])
    data["cutoff_date"] = parse_port_date(data["general_cutoff"])
    data["receiving_window"] = (
        f"Empty start: {data['empty_start']}; "
        f"General ERD: {data['general_erd']}; Reefer ERD: {data['reefer_erd']}; Haz ERD: {data['haz_erd']}; "
        f"General cutoff: {data['general_cutoff']}; Reefer cutoff: {data['reefer_cutoff']}; Haz cutoff: {data['haz_cutoff']}"
    )

    return data


def bool_from_ready(value):
    value = clean_text(value).lower()
    return value.startswith("y") or value in ("true", "ready", "1")


def first_value(data, *names):
    for name in names:
        value = clean_text(data.get(name))
        if value:
            return value
    return ""


def get_container_details(page, container):
    url = CONTAINER_URL.format(container=container)
    print(f"Getting container availability data for {container}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.get_by_text("Agree", exact=True).click(timeout=3000)
    except PlaywrightError:
        pass

    table = page.locator("#inquiries-container-availability-table").first
    try:
        table.wait_for(state="attached", timeout=30000)
    except PlaywrightTimeoutError:
        body_text = clean_text(page.locator("body").inner_text(timeout=10000))
        return {
            "found": False,
            "container": container,
            "notes": (
                f"Container {container} not found in public port availability inquiry."
                if "not found" in body_text.lower()
                else f"Container {container} availability table did not load in public port inquiry."
            ),
        }

    row = table_row_dict(table)

    vessel_voyage = first_value(row, "Vessel/Voyage", "Vessel / Voyage", "Vessel Voyage")
    vessel = first_value(row, "Vessel")
    voyage = first_value(row, "Voyage", "Voyage#")
    if vessel_voyage and "/" in vessel_voyage:
        vessel_part, voyage_part = vessel_voyage.split("/", 1)
        vessel = vessel or clean_text(vessel_part)
        voyage = voyage or clean_text(voyage_part)

    data = {
        "found": True,
        "ready_text": first_value(row, "Ready for Delivery", "Ready", "Available"),
        "ready": bool_from_ready(first_value(row, "Ready for Delivery", "Ready", "Available")),
        "container": first_value(row, "Container#", "Container", "Container Number") or container,
        "line_status": first_value(row, "Line Status", "Line"),
        "customs_status": first_value(row, "Customs Status", "Customs"),
        "other_holds": first_value(row, "Other Holds", "Holds"),
        "location": first_value(row, "Location"),
        "position": first_value(row, "Position"),
        "ptd": first_value(row, "PTD"),
        "lfd": first_value(row, "LFD", "Last Free Day"),
        "term_dem": first_value(row, "Term Dem", "Terminal Demurrage"),
        "non_dem": first_value(row, "Non Dem", "Non-Demurrage"),
        "size": first_value(row, "Size", "Equipment Size", "Equipment"),
        "ship": vessel,
        "voyage": voyage,
    }
    data["lfd_date"] = parse_port_date(data["lfd"])
    return data


def get_bol_details(page, bol):
    url = BOL_URL.format(bol=bol)
    print(f"Getting BOL availability data for {bol}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.get_by_text("Agree", exact=True).click(timeout=3000)
    except PlaywrightError:
        pass

    try:
        page.wait_for_function(
            """() => document.querySelector('#inquiries-bol-availability-table')
                || document.querySelector('#inquiries-container-availability-table')
                || document.querySelector("table[id*='availability']")
                || document.body.innerText.toLowerCase().includes('not found')""",
            timeout=60000,
        )
    except PlaywrightTimeoutError:
        pass

    body_text = clean_text(page.locator("body").inner_text(timeout=10000))
    table = page.locator(
        "#inquiries-bol-availability-table, #inquiries-container-availability-table, table[id*='availability']"
    ).first
    if "not found" in body_text.lower() or table.count() == 0:
        return {
            "found": False,
            "bol": bol,
            "notes": f"BOL {bol} not found in public port availability inquiry.",
        }

    table.wait_for(state="attached", timeout=20000)
    row = table_row_dict(table)
    vessel_voyage = first_value(row, "Vessel/Voyage", "Vessel / Voyage", "Vessel Voyage")
    vessel = first_value(row, "Vessel", "Vessel Name")
    voyage = first_value(row, "Voyage", "Voyage#")
    if vessel_voyage and "/" in vessel_voyage:
        vessel_part, voyage_part = vessel_voyage.split("/", 1)
        vessel = vessel or clean_text(vessel_part)
        voyage = voyage or clean_text(voyage_part)

    data = {
        "found": True,
        "bol": bol,
        "shipline": first_value(row, "SSCO", "Shipline", "Line"),
        "ship": vessel,
        "voyage": voyage,
        "container": first_value(row, "Container#", "Container", "Container Number"),
        "line_status": first_value(row, "Line Status", "Line"),
        "customs_status": first_value(row, "Customs Status", "Customs"),
        "other_holds": first_value(row, "Other Holds", "Holds"),
        "location": first_value(row, "Location"),
        "lfd": first_value(row, "LFD", "Last Free Day"),
        "size": first_value(row, "Size", "Equipment Size", "Equipment"),
    }
    data["lfd_date"] = parse_port_date(data["lfd"])
    return data


def get_ecces_details(page, container, bol=""):
    container = clean_text(container).upper()
    bol = clean_text(bol)
    url = ECCES_API_URL.format(container=quote_plus(container), bol=quote_plus(bol))
    print(f"Getting ECCES data for {container}")

    response = page.request.get(url, timeout=60000)
    if response.status in (403, 429, 503):
        page.goto(ECCES_LOOKUP_URL, wait_until="networkidle", timeout=60000)
        response = page.request.get(url, timeout=60000)

    if not response.ok:
        return {
            "found": False,
            "container": container,
            "notes": f"ECCES lookup failed for {container}: HTTP {response.status}.",
        }

    try:
        records = response.json()
    except Exception:
        records = json.loads(response.text())

    if not records:
        return {
            "found": False,
            "container": container,
            "notes": f"ECCES lookup returned no records for {container}.",
        }

    record = records[0]
    return {
        "found": True,
        "container": clean_text(record.get("containerNumber")) or container,
        "bol": clean_text(record.get("billOfLading")),
        "shipline": clean_text(record.get("steamshipLine")),
        "container_type": clean_text(record.get("containerType")),
        "chassis": clean_text(record.get("chassisNumber")),
        "avail_terminal": combined_date_time(record, "availableAtTerminalDate", "availableAtTerminalTime"),
        "ces_gate_in": combined_date_time(record, "cesGateInDate", "cesGateInTime"),
        "cbp_exam_complete": combined_date_time(record, "cbpExamCompleteDate", "cbpExamCompleteTime"),
        "customs_release": clean_text(record.get("customsReleaseDate")),
        "freight_release": clean_text(record.get("freightReleaseDate")),
        "notes": clean_text(record.get("notes")),
    }


def order_release_number(order):
    row = db.session.execute(
        text("SELECT `Release` FROM orders WHERE id = :order_id"),
        {"order_id": order.id},
    ).mappings().first()
    if row:
        value = clean_text(row.get("Release"))
        if value and value.lower() not in ("0", "1", "false", "true", "none"):
            return value
    return clean_text(getattr(order, "Release", None))


def ship_arrival_date(ship, voyage):
    ship = clean_text(ship)
    voyage = clean_text(voyage)
    if not ship or not voyage:
        return None, ""

    row = db.session.execute(
        text("""
            SELECT ActArrival, EstArrival
            FROM ships
            WHERE LOWER(TRIM(Vessel)) = LOWER(TRIM(:ship))
              AND (
                    LOWER(TRIM(VoyageIn)) = LOWER(TRIM(:voyage))
                 OR LOWER(TRIM(VoyageOut)) = LOWER(TRIM(:voyage))
              )
            ORDER BY id DESC
            LIMIT 1
        """),
        {"ship": ship, "voyage": voyage},
    ).mappings().first()
    if not row:
        return None, ""

    arrival_text = clean_text(row.get("ActArrival")) or clean_text(row.get("EstArrival"))
    return parse_port_date(arrival_text), arrival_text


def ensure_review_log_table():
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS dispatch_kanban_state (
            id INT AUTO_INCREMENT PRIMARY KEY,
            OrderId INT NOT NULL UNIQUE,
            WorkflowStatus VARCHAR(45) NOT NULL,
            Notes TEXT,
            PinReference VARCHAR(100),
            BillingStatus VARCHAR(100),
            CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_dispatch_kanban_order (OrderId),
            INDEX idx_dispatch_kanban_status (WorkflowStatus)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS dispatch_kanban_review_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            OrderId INT NOT NULL,
            ReviewDate DATE,
            ReviewType VARCHAR(45),
            Shipline VARCHAR(100),
            Ship VARCHAR(100),
            Voyage VARCHAR(100),
            ArrivalDate DATE,
            ERDDate DATE,
            CutoffDate DATE,
            LineStatus VARCHAR(100),
            CustomsStatus VARCHAR(100),
            OtherHolds VARCHAR(255),
            EquipmentSize VARCHAR(100),
            ReadyForDelivery VARCHAR(45),
            Location VARCHAR(100),
            LFDDate DATE,
            ECCESContainerType VARCHAR(100),
            ECCESChassis VARCHAR(100),
            ECCESAvailTerminal VARCHAR(100),
            ECCESGateIn VARCHAR(100),
            ECCESCBPExamComplete VARCHAR(100),
            ECCESCustomsRelease VARCHAR(100),
            ECCESFreightRelease VARCHAR(100),
            Notes TEXT,
            Username VARCHAR(45),
            CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_dispatch_kanban_review_order (OrderId),
            INDEX idx_dispatch_kanban_review_created (CreatedAt)
        )
    """))
    existing_columns = {
        row[0]
        for row in db.session.execute(text("SHOW COLUMNS FROM dispatch_kanban_review_log")).fetchall()
    }
    for column_name, column_def in {
        "LineStatus": "VARCHAR(100)",
        "CustomsStatus": "VARCHAR(100)",
        "OtherHolds": "VARCHAR(255)",
        "EquipmentSize": "VARCHAR(100)",
        "ReadyForDelivery": "VARCHAR(45)",
        "Location": "VARCHAR(100)",
        "LFDDate": "DATE",
        "ECCESContainerType": "VARCHAR(100)",
        "ECCESChassis": "VARCHAR(100)",
        "ECCESAvailTerminal": "VARCHAR(100)",
        "ECCESGateIn": "VARCHAR(100)",
        "ECCESCBPExamComplete": "VARCHAR(100)",
        "ECCESCustomsRelease": "VARCHAR(100)",
        "ECCESFreightRelease": "VARCHAR(100)",
    }.items():
        if column_name not in existing_columns:
            db.session.execute(text(f"ALTER TABLE dispatch_kanban_review_log ADD COLUMN {column_name} {column_def}"))
    db.session.commit()


def order_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def log_review(order, data, notes, review_type="New Order Booking Review"):
    db.session.execute(
        text("""
            INSERT INTO dispatch_kanban_review_log
                (OrderId, ReviewDate, ReviewType, Shipline, Ship, Voyage, ArrivalDate, ERDDate, CutoffDate,
                 LineStatus, CustomsStatus, OtherHolds, EquipmentSize, ReadyForDelivery, Location, LFDDate, Notes,
                 Username, CreatedAt)
            VALUES
                (:order_id, :review_date, :review_type, :shipline, :ship, :voyage, :arrival_date, :erd_date,
                 :cutoff_date, :line_status, :customs_status, :other_holds, :equipment_size, :ready_for_delivery,
                 :location, :lfd_date, :notes, :username, :created_at)
        """),
        {
            "order_id": order.id,
            "review_date": TODAY,
            "review_type": review_type,
            "shipline": clean_text(data.get("shipline") or order.SSCO),
            "ship": clean_text(data.get("ship") or order.Ship),
            "voyage": clean_text(data.get("voyage") or order.Voyage),
            "arrival_date": data.get("arrival_date") or order_date(order.Date6),
            "erd_date": data.get("erd_date") or order_date(order.Date4),
            "cutoff_date": data.get("cutoff_date") or order_date(order.Date5),
            "line_status": clean_text(data.get("line_status")),
            "customs_status": clean_text(data.get("customs_status")),
            "other_holds": clean_text(data.get("other_holds")),
            "equipment_size": clean_text(data.get("equipment_size") or data.get("size")),
            "ready_for_delivery": clean_text(data.get("ready_text") or data.get("ready_for_delivery") or data.get("ready")),
            "location": clean_text(data.get("location")),
            "lfd_date": data.get("lfd_date") or data.get("cutoff_date"),
            "notes": notes,
            "username": "booking-review-agent",
            "created_at": datetime.utcnow(),
        },
    )


def log_ecces_review(order, data):
    if data.get("found"):
        notes = (
            f"ECCES container {clean_text(data.get('container'))} reviewed. "
            f"Avail Terminal: {clean_text(data.get('avail_terminal'))}; "
            f"CES Gate In: {clean_text(data.get('ces_gate_in'))}; "
            f"CBP Exam Complete: {clean_text(data.get('cbp_exam_complete'))}; "
            f"Customs Release: {clean_text(data.get('customs_release'))}; "
            f"Freight Release: {clean_text(data.get('freight_release'))}."
        )
        if clean_text(data.get("notes")):
            notes = f"{notes} Notes: {clean_text(data.get('notes'))}."
    else:
        notes = data.get("notes") or f"ECCES lookup returned no data for {clean_text(order.Container)}."

    db.session.execute(
        text("""
            INSERT INTO dispatch_kanban_review_log
                (OrderId, ReviewDate, ReviewType, Shipline, ECCESContainerType, ECCESChassis,
                 ECCESAvailTerminal, ECCESGateIn, ECCESCBPExamComplete, ECCESCustomsRelease,
                 ECCESFreightRelease, Notes, Username, CreatedAt)
            VALUES
                (:order_id, :review_date, :review_type, :shipline, :container_type, :chassis,
                 :avail_terminal, :ces_gate_in, :cbp_exam_complete, :customs_release,
                 :freight_release, :notes, :username, :created_at)
        """),
        {
            "order_id": order.id,
            "review_date": TODAY,
            "review_type": "ECCES Review",
            "shipline": clean_text(data.get("shipline") or order.SSCO),
            "container_type": clean_text(data.get("container_type")),
            "chassis": clean_text(data.get("chassis")),
            "avail_terminal": clean_text(data.get("avail_terminal")),
            "ces_gate_in": clean_text(data.get("ces_gate_in")),
            "cbp_exam_complete": clean_text(data.get("cbp_exam_complete")),
            "customs_release": clean_text(data.get("customs_release")),
            "freight_release": clean_text(data.get("freight_release")),
            "notes": notes,
            "username": "booking-review-agent",
            "created_at": datetime.utcnow(),
        },
    )
    db.session.commit()
    return notes


def update_order(order, data):
    changes = []

    erd_date = data.get("erd_date")
    cutoff_date = data.get("cutoff_date")

    if erd_date and date_changed(order.Date4, erd_date):
        changes.append(f"ERD {order_date(order.Date4)} -> {erd_date}")
        order.Date4 = erd_date

    if cutoff_date and date_changed(order.Date5, cutoff_date):
        changes.append(f"Cutoff {order_date(order.Date5)} -> {cutoff_date}")
        order.Date5 = cutoff_date

    for attr, key in (("SSCO", "shipline"), ("Ship", "ship"), ("Voyage", "voyage")):
        value = clean_text(data.get(key))
        if value and clean_text(getattr(order, attr, None)) != value:
            changes.append(f"{attr} {clean_text(getattr(order, attr, None))} -> {value}")
            setattr(order, attr, value)

    con_type = " ".join(part for part in [data.get("length"), data.get("type"), data.get("height")] if clean_text(part))
    con_type = clean_text(con_type)
    if con_type and clean_text(order.Type) != con_type:
        changes.append(f"Type {clean_text(order.Type)} -> {con_type}")
        order.Type = con_type

    notes = (
        f"Booking {strip_booking(order.Booking)} reviewed. "
        f"{data.get('receiving_window')}. "
        f"Total: {data.get('total')}; Received: {data.get('received')}; Delivered: {data.get('delivered')}."
    )
    if changes:
        notes = f"{notes} Changes: {'; '.join(changes)}."
    else:
        notes = f"{notes} No order field changes."

    log_review(order, data, notes)
    db.session.commit()
    return notes


def update_import_order(order, data):
    changes = []

    if not data.get("found"):
        notes = data.get("notes") or f"Container {clean_text(order.Container)} not found."
        log_review(order, data, notes, review_type="New Import Availability Review")
        db.session.commit()
        return notes

    lfd_date = data.get("lfd_date")
    if lfd_date and date_changed(order.Date5, lfd_date):
        changes.append(f"LFD {order_date(order.Date5)} -> {lfd_date}")
        order.Date5 = lfd_date

    arrival_date = data.get("arrival_date")
    if arrival_date and date_changed(order.Date6, arrival_date):
        changes.append(f"Ship arrival {order_date(order.Date6)} -> {arrival_date}")
        order.Date6 = arrival_date

    for attr, key in (("SSCO", "shipline"), ("Ship", "ship"), ("Voyage", "voyage"), ("Type", "size")):
        value = clean_text(data.get(key))
        if value and clean_text(getattr(order, attr, None)) != value:
            changes.append(f"{attr} {clean_text(getattr(order, attr, None))} -> {value}")
            setattr(order, attr, value)

    notes = (
        f"Container {clean_text(data.get('container')) or clean_text(order.Container)} availability reviewed. "
        f"Pre-arrival: {'Yes' if data.get('pre_arrival') else 'No'}; "
        f"Ready: {clean_text(data.get('ready_text')) or data.get('ready')}; "
        f"Line Status: {clean_text(data.get('line_status'))}; "
        f"Customs Status: {clean_text(data.get('customs_status'))}; "
        f"Other Holds: {clean_text(data.get('other_holds'))}; "
        f"Location: {clean_text(data.get('location'))}; "
        f"LFD: {clean_text(data.get('lfd'))}; "
        f"Equipment: {clean_text(data.get('size'))}; "
        f"Vessel/Voyage: {clean_text(data.get('ship'))}/{clean_text(data.get('voyage'))}; "
        f"Ship Arrival: {clean_text(data.get('arrival_text')) or data.get('arrival_date') or ''}."
    )
    if clean_text(data.get("notes")):
        notes = f"{notes} {clean_text(data.get('notes'))}"
    if changes:
        notes = f"{notes} Changes: {'; '.join(changes)}."
    else:
        notes = f"{notes} No order field changes."

    review_data = {
        "shipline": data.get("shipline"),
        "ship": data.get("ship"),
        "voyage": data.get("voyage"),
        "arrival_date": data.get("arrival_date"),
        "cutoff_date": data.get("lfd_date") or order_date(order.Date5),
        "line_status": data.get("line_status"),
        "customs_status": data.get("customs_status"),
        "other_holds": data.get("other_holds"),
        "equipment_size": data.get("size"),
        "ready_for_delivery": data.get("ready_text") or data.get("ready"),
        "location": data.get("location"),
        "lfd_date": data.get("lfd_date") or order_date(order.Date5),
    }
    log_review(order, review_data, notes, review_type="New Import Availability Review")
    db.session.commit()
    return notes


def get_review_orders():
    attempts = 0
    while attempts < 4:
        try:
            on_call_import_non_ecces = (
                (Orders.DisStatus == "on_call")
                & (Orders.HaulType.contains("Import"))
                & ((Orders.HoldType != "ECCES") | (Orders.HoldType == None))
            )
            return Orders.query.filter(
                Orders.DisStatus.in_(REVIEW_STATUSES) | on_call_import_non_ecces
            ).order_by(Orders.id.asc()).all()
        except Exception as exc:
            attempts += 1
            print(f"Could not query Orders on try {attempts}: {exc}")
            time.sleep(1)
    return []


def get_ecces_orders():
    attempts = 0
    while attempts < 4:
        try:
            return Orders.query.filter(
                (Orders.HoldType == "ECCES")
                & ((Orders.Hstat < 2) | (Orders.Hstat == None))
            ).order_by(Orders.id.asc()).all()
        except Exception as exc:
            attempts += 1
            print(f"Could not query ECCES Orders on try {attempts}: {exc}")
            time.sleep(1)
    return []


def main():
    print(" ")
    print("_______________________________________________________")
    print(f"This sequence run date: {RUN_AT}")
    print("_______________________________________________________")
    print(" ")

    ensure_review_log_table()
    orders = get_review_orders()
    ecces_orders = get_ecces_orders()
    status_labels = ", ".join(REVIEW_STATUS_LABELS[status] for status in REVIEW_STATUSES)
    status_labels = f"{status_labels}, {ON_CALL_IMPORT_LABEL}"
    print(f"Found {len(orders)} orders in Kanban review sections: {status_labels}")
    print(f"Found {len(ecces_orders)} active orders with HoldType == ECCES")
    if not orders and not ecces_orders:
        return

    print("Using public lookup pages; no TOS login required")
    playwright, browser, page = launch_browser()
    try:
        for order in orders:
            haul_type = clean_text(order.HaulType).lower()

            try:
                if "export" in haul_type:
                    booking = strip_booking(order.Booking)
                    if not hasinput(booking):
                        notes = "Booking review skipped: export order has no booking number."
                        print(f"JO {order.Jo}: {notes}")
                        log_review(order, {}, notes)
                        db.session.commit()
                        continue
                    data = get_booking_details(page, booking)
                    notes = update_order(order, data)
                elif "import" in haul_type:
                    container = clean_text(order.Container)
                    if not hasinput(container):
                        notes = "Import availability review skipped: import order has no container number."
                        print(f"JO {order.Jo}: {notes}")
                        log_review(order, {}, notes, review_type="New Import Availability Review")
                        db.session.commit()
                        continue
                    data = get_container_details(page, container)
                    location = clean_text(data.get("location")).lower()
                    pre_arrival = (not data.get("found")) or location == "vessel"
                    if pre_arrival:
                        data["pre_arrival"] = True
                        release_number = order_release_number(order)
                        if hasinput(release_number):
                            bol_data = get_bol_details(page, release_number)
                            if bol_data.get("found"):
                                base_data = data if data.get("found") else {"found": True, "container": container}
                                data = merge_values(
                                    base_data,
                                    bol_data,
                                    (
                                        "shipline",
                                        "ship",
                                        "voyage",
                                        "line_status",
                                        "customs_status",
                                        "other_holds",
                                        "location",
                                        "lfd",
                                        "lfd_date",
                                        "size",
                                    ),
                                )
                                data["pre_arrival"] = True
                                data["notes"] = (
                                    f"Pre-arrival import; used BOL {release_number} availability lookup."
                                )
                        arrival_date, arrival_text = ship_arrival_date(data.get("ship"), data.get("voyage"))
                        data["arrival_date"] = arrival_date
                        data["arrival_text"] = arrival_text
                    vessel_name = clean_text(data.get("ship"))
                    if vessel_name:
                        unload_dates = get_ports_america_unload_dates(page, vessel_name)
                        if len(unload_dates) > 1:
                            unload_note = format_unload_note(unload_dates)
                            if append_kanban_note_once(order, unload_note):
                                print(f"JO {order.Jo}: added Kanban note {unload_note}")
                    notes = update_import_order(order, data)
                else:
                    notes = f"Review skipped: unsupported HaulType {clean_text(order.HaulType)}."
                    print(f"JO {order.Jo}: {notes}")
                    log_review(order, {}, notes)
                    db.session.commit()
                    continue
                print(f"JO {order.Jo}: {notes}")
            except Exception as exc:
                notes = f"Kanban review failed: {exc}"
                print(f"JO {order.Jo}: {notes}")
                log_review(order, {}, notes)
                db.session.commit()
        for order in ecces_orders:
            try:
                container = clean_text(order.Container)
                if not hasinput(container):
                    data = {
                        "found": False,
                        "container": "",
                        "notes": "ECCES review skipped: order has no container number.",
                    }
                else:
                    data = get_ecces_details(page, container)
                notes = log_ecces_review(order, data)
                print(f"JO {order.Jo}: {notes}")
            except Exception as exc:
                notes = f"ECCES review failed: {exc}"
                print(f"JO {order.Jo}: {notes}")
                log_ecces_review(order, {"found": False, "container": clean_text(order.Container), "notes": notes})
    finally:
        browser.close()
        playwright.stop()
        if nt == "remote":
            tunnel.stop()


if __name__ == "__main__":
    main()
