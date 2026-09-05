import os
import sys
import socket
from utils import getpaths
import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument default is oslm')
    scac = 'oslm'

scac = scac.upper()
try:
    nt = sys.argv[2]
except:
    nt = 'remote'

try:
    run_mode = sys.argv[3].lower()
except:
    run_mode = 'live'

GLOBAL_TEST_MODE = run_mode in ('test', 'review', 'dryrun')

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running FFF_emailread_daily for {scac} in tunnel mode: {nt} and run mode: {run_mode}')

    host_name = socket.gethostname()
    print("Host Name:", host_name)
    dropbox_path = getpaths(host_name, 'dropbox')
    sys_path = getpaths(host_name, 'system')
    sys.path.append(sys_path) #So we can import CCC_system_setup from full path

    os.environ['SCAC'] = scac
    os.environ['PURPOSE'] = 'script'
    os.environ['MACHINE'] = host_name
    os.environ['TUNNEL'] = nt

    from remote_db_connect import db
    if nt == 'remote': from remote_db_connect import tunnel
    from models8 import Interchange, Orders, Drivers, Pins, Drops, People, PortClosed
    from CCC_system_setup import usernames, passwords, websites, addpath3, imap_url, scac, companydata, nt
    from email_reports import emailtxt
    from cronfuncs import conmatch
else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

import fnmatch
import subprocess
import imaplib, email
import datetime
import re
import numpy as np
from cronfuncs import newjo
from datetime import timedelta

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.path.dirname(__file__), ".ms-playwright"))
try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:
    PlaywrightError = None
    PlaywrightTimeoutError = Exception
    sync_playwright = None

booking_p = re.compile(
    r"(?<![A-Z0-9])(?:"
    r"EBKG[A-Z0-9]{8}|"
    r"[1259][0-9]{8}|"
    r"[1-9][0-9]{7}(?:-[0-9]+)?|"
    r"[012][PHL0-9]{9}|"
    r"S[-0-9]{10}|"
    r"S[0-9]{9}|"
    r"[0O][0-9VRO]{11}|"
    r"NHOBJ[0-9]{6}"
    r")(?![A-Z0-9])",
    re.IGNORECASE,
)
container_p = re.compile(r"\b[A-Z]{4}[0-9]{7}\b", re.IGNORECASE)

#_____________________________________________________________________________________________________________
# Switches for routines
#_____________________________________________________________________________________________________________
remit=0
gjob=1
gbook=0
kjob=0
cdata = companydata()
tcode= cdata[10]
booking_review_playwright = None
booking_review_browser = None
booking_review_page = None
AUTO_GLOBAL_HOLD_TYPES = {"Unavailable", "Before ERD", "Past Cutoff"}
global_report_rows = []
global_report_text_lines = []
global_report_text_seen = set()
latest_global_marker = ''
latest_global_index = None
process_latest_global_ops = False
latest_global_execution_date = None
# 0 means do not run, 1 means run normal, 2 means create new baseline
#_____________________________________________________________________________________________________________
# Hold Tunnel Open to Ensure Links
from cronfuncs import tunneltest
success = tunneltest()
#_____________________________________________________________________________________________________________

def unique(list1):
    x = np.array(list1)
    newlist=np.unique(x)
    return newlist

def get_bookings(longs):
    return [normalize_booking(match) for match in booking_p.findall(longs)]

def normalize_booking(booking):
    booking = booking.strip().upper()
    if booking.startswith('S'):
        booking = booking.replace('-', '')
    elif re.search(r'^[0-9]{8}-[0-9]+$', booking):
        booking = re.sub(r'-[0-9]+$', '', booking)
    return booking

def clean_port_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def parse_port_date(value):
    value = clean_port_text(value)
    if not value or value.upper() == "NOF":
        return None
    value = value.split(" ", 1)[0]
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None

def parse_port_int(value):
    value = clean_port_text(value)
    if not value:
        return None
    value = re.sub(r"[^0-9]", "", value)
    return int(value) if value else None

def default_global_port_data():
    return {
        "valid": False,
        "total": None,
        "received": None,
        "delivered": None,
        "shipline": "",
        "ship": "",
        "voyage": "",
        "general_erd": "",
        "general_cutoff": "",
        "erd_date": None,
        "cutoff_date": None,
    }

def booking_window_good(port_data, execution_date, port_check_failed=False):
    return not port_check_failed and global_load_in_hold_type(port_data, execution_date) is None

def launch_booking_review_browser():
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed in flaskenv")
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        chromium_sandbox=False,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-seccomp-filter-sandbox"],
    )
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    return playwright, browser, page

def booking_review_page_for_global():
    global booking_review_playwright, booking_review_browser, booking_review_page
    if booking_review_page is None:
        booking_review_playwright, booking_review_browser, booking_review_page = launch_booking_review_browser()
    return booking_review_page

def cell_texts(table_locator):
    rows = table_locator.locator("tbody tr")
    if rows.count() == 0:
        return []
    cells = rows.first.locator("td")
    return [clean_port_text(cells.nth(ix).inner_text(timeout=2000)) for ix in range(cells.count())]

def table_row_dict(table_locator):
    headers = []
    header_cells = table_locator.locator("thead th")
    for ix in range(header_cells.count()):
        headers.append(clean_port_text(header_cells.nth(ix).inner_text(timeout=2000)))
    values = cell_texts(table_locator)
    return {header: values[ix] if ix < len(values) else "" for ix, header in enumerate(headers)}

def get_global_booking_port_data(booking):
    page = booking_review_page_for_global()
    url = f"https://www.portsamerica.com/resources/inquiries?location=SGT_BAL&option=bookingInquiry&numbers={booking}"
    print(f"Checking port booking availability for Global booking {booking}", flush=True)
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

    vessel_table = page.locator("table[id^='inquiries-booking-vessel-info-table']").first
    vessel_table.wait_for(state="attached", timeout=10000)
    detail_table = page.locator("table[id^='inquiries-booking-info-table']").first
    detail_table.wait_for(state="attached", timeout=10000)

    vessel_data = table_row_dict(vessel_table)
    detail_data = table_row_dict(detail_table)
    total = parse_port_int(detail_data.get("Total"))
    received = parse_port_int(detail_data.get("#Received"))
    delivered = parse_port_int(detail_data.get("#Delivered") or detail_data.get("Delivered"))
    valid = total is not None and received is not None and total > received

    return {
        "valid": valid,
        "total": total,
        "received": received,
        "delivered": delivered,
        "shipline": vessel_data.get("SSCO", ""),
        "ship": vessel_data.get("Vessel Name", ""),
        "voyage": vessel_data.get("Voyage#", ""),
        "general_erd": vessel_data.get("General Begin Receive", ""),
        "general_cutoff": vessel_data.get("General Cutoff", ""),
        "erd_date": parse_port_date(vessel_data.get("General Begin Receive")),
        "cutoff_date": parse_port_date(vessel_data.get("General Cutoff")),
    }

def close_booking_review_browser():
    global booking_review_playwright, booking_review_browser, booking_review_page
    if booking_review_browser is not None:
        booking_review_browser.close()
    if booking_review_playwright is not None:
        booking_review_playwright.stop()
    booking_review_playwright = None
    booking_review_browser = None
    booking_review_page = None

def get_body(msg):
    if msg.is_multipart():
        return get_body(msg.get_payload(0))
    else:
        return msg.get_payload(None,True)

def search(key,value,con):
    result,data=con.search(None,key,'"{}"'.format(value))
    return data

#(_, data) = CONN.search(None, '(SENTSINCE {0})'.format(date)), '(FROM {0})'.format("someone@yahoo.com") )
def search_from_date(key,value,con,datefrom):
    result,data=con.search( None, '(SENTSINCE {0})'.format(datefrom) , key, '"{}"'.format(value) )
    return data

def get_emails(result_bytes,con):
    msgs=[]
    for num in result_bytes[0].split():
        typ,data=con.fetch(num,'(RFC822)')
        msgs.append(data)
    return msgs

def get_attachments(msg):
    attachment_dir='/home/mark/alldocs/test'
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()
        if bool(file_Name):
            filePath=os.path.join(attachment_dir,file_Name)
            with open(filePath,'wb')as f:
                f.write(part.get_payload(decode=True))

def get_attachments_name(msg,this_name,att_dir):
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()
        if bool(file_Name):
            filePath=os.path.join(att_dir,this_name)
            with open(filePath,'wb')as f:
                f.write(part.get_payload(decode=True))

def get_attachments_pdf(msg,att_dir,type,contains):
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()

        if bool(file_Name):
            if type in file_Name.lower() and contains in file_Name:
                filePath=os.path.join(att_dir,file_Name)
                with open(filePath,'wb')as f:
                    f.write(part.get_payload(decode=True))

def get_attachment_filename(msg,type,contains):
    filehere=[]
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()
        if bool(file_Name):
            if type in file_Name.lower() and contains.lower() in file_Name.lower():
                filehere.append(file_Name)

    return filehere

def datename(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            part = response_part[1].decode('utf-8')
            msg = email.message_from_string(part)
            date=msg['Date']
            #print(date)
            date=date.split('-',1)[0]
            date=date.split('+',1)[0]
            date=date.strip()
            n=datetime.datetime.strptime(date , "%a, %d %b %Y %H:%M:%S")
            adder=str(n.year)+'_'+str(n.month)+'_'+str(n.day)+'_'+str(n.hour)+str(n.minute)+str(n.second)
    return adder

def get_date(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            try:
                part = response_part[1].decode('utf-8')
                msg = email.message_from_string(part)
                date=msg['Date']
                date=date.split('-',1)[0]
                date=date.split('+',1)[0]
                date=date.strip()
                n=datetime.datetime.strptime(date , "%a, %d %b %Y %H:%M:%S")
                newdate=datetime.date(n.year,n.month,n.day)
            except:
                newdate=None
    return newdate

def get_datetime(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            try:
                part = response_part[1].decode('utf-8')
                msg = email.message_from_string(part)
                date=msg['Date']
                date=date.split('-',1)[0]
                date=date.split('+',1)[0]
                date=date.strip()
                return datetime.datetime.strptime(date , "%a, %d %b %Y %H:%M:%S")
            except:
                return None
    return None

def get_message_id(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            try:
                part = response_part[1].decode('utf-8')
                msg = email.message_from_string(part)
                return clean_port_text(msg.get('Message-ID') or msg.get('Message-Id') or '')
            except:
                return ''
    return ''

def get_subject(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            part = response_part[1].decode('utf-8')
            msg = email.message_from_string(part)
            subject=msg['Subject']
    return subject

def get_body_text(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            part = response_part[1].decode('utf-8')
            msg = email.message_from_string(part)
            text=msg['Text']
    return text

def checkdate(emaildate,filename,txtfile):
    returnval=0
    with open(txtfile) as f:
        for line in f:
            if filename in line:
                linelist=line.split()
                date=linelist[0]
                if date != 'None':
                    datedt=datetime.datetime.strptime(date, '%Y-%m-%d')
                    datedt=datedt.date()
                    if datedt<emaildate:
                        #print('File needs to be updated',datedt,date,filename)
                        returnval=1
                else:
                    #print('File found, but have no date to compare')
                    returnval=1
    return returnval

def next_business_day(date, jx):
    next_day = date
    kx = 0
    for ix in range(15):
        next_day = next_day + timedelta(days=1)
        pdat = PortClosed.query.filter(PortClosed.Date==next_day).first()
        if pdat is None:
            kx += 1
            if kx == jx: return next_day

def next_global_execution_date(email_date):
    next_day = email_date + timedelta(days=1)
    if next_day.weekday() < 5:
        return next_day

    for ix in range(15):
        next_day = next_day + timedelta(days=1)
        pdat = PortClosed.query.filter(PortClosed.Date==next_day).first()
        if next_day.weekday() < 5 and pdat is None:
            return next_day
    return next_business_day(email_date, 1)

def plan_order_value(date):
    return f"Plan {date.strftime('%a')} {date.strftime('%b')[0]}{date.day}"

def global_booking_hold_type(port_data, execution_date, port_check_failed=False):
    if port_check_failed or not port_data.get("valid"):
        return "Unavailable"

    return global_booking_window_hold_type(port_data, execution_date)

def global_load_in_hold_type(port_data, execution_date, port_check_failed=False):
    if port_check_failed:
        return "Unavailable"
    total = port_data.get("total")
    received = port_data.get("received")
    if total is not None and received is not None and total <= received:
        return "Unavailable"
    return global_booking_window_hold_type(port_data, execution_date)

def global_booking_window_hold_type(port_data, execution_date):
    erd_date = port_data.get("erd_date")
    cutoff_date = port_data.get("cutoff_date")
    if erd_date and execution_date < erd_date:
        return "Before ERD"
    if cutoff_date and execution_date > cutoff_date:
        return "Past Cutoff"
    return None

def global_empty_out_hold_type(port_data, execution_date, port_check_failed=False):
    if port_check_failed:
        return "Unavailable"
    total = port_data.get("total")
    delivered = port_data.get("delivered")
    if total is not None and delivered is not None and total <= delivered:
        return "Unavailable"
    return global_booking_window_hold_type(port_data, execution_date)

def global_unavailable_reason(booking_role, port_data):
    total = port_data.get("total")
    received = port_data.get("received")
    delivered = port_data.get("delivered")
    if booking_role == "load_in":
        return f"total={total} received={received}"
    if booking_role == "empty_out":
        return f"total={total} delivered={delivered}"
    return f"total={total} received={received} delivered={delivered}"

def global_booking_role_from_lines(booking, bodylines):
    booking_role = "booking"
    size = "40"
    for line in bodylines:
        line_bookings = get_bookings(line)
        if booking in line_bookings:
            booking_role = combine_global_roles(booking_role, global_line_role(line))
            if "40'" in line or "40" in line:
                size = "40"
            if "20'" in line or "20" in line:
                size = "20"
    return booking_role, size

def global_effective_report_role(booking_role, order=None):
    if booking_role != "mixed":
        return booking_role
    if order is not None and clean_port_text(getattr(order, "Container", "")):
        return "load_in"
    return "booking"

def date_value(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    return value

def update_global_order_from_port(order, port_data, execution_date, port_check_failed=False, hold_type=None):
    if hold_type is None:
        hold_type = global_booking_hold_type(port_data, execution_date, port_check_failed)
    changes = []

    field_updates = [
        ("Date4", port_data.get("erd_date"), "ERD"),
        ("Date5", port_data.get("cutoff_date"), "Cutoff"),
        ("SSCO", port_data.get("shipline"), "SSCO"),
        ("Ship", port_data.get("ship"), "Ship"),
        ("Voyage", port_data.get("voyage"), "Voyage"),
    ]
    for attr, value, label in field_updates:
        if value is None or value == "":
            continue
        old_value = getattr(order, attr, None)
        if date_value(old_value) != value:
            setattr(order, attr, value)
            changes.append(f"{label} {old_value} -> {value}")

    old_hold = getattr(order, "HoldType", None)
    if hold_type:
        if old_hold != hold_type:
            order.HoldType = hold_type
            changes.append(f"HoldType {old_hold} -> {hold_type}")
    elif old_hold in AUTO_GLOBAL_HOLD_TYPES:
        order.HoldType = None
        changes.append(f"HoldType {old_hold} -> None")

    return changes, hold_type

def format_report_date(value):
    value = date_value(value)
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    return clean_port_text(value)

def global_window_status(hold_type, port_check_failed=False):
    if port_check_failed:
        return "Port check failed"
    if hold_type == "Unavailable":
        return "Not good - unavailable"
    if hold_type == "Before ERD":
        return "Not good - before ERD"
    if hold_type == "Past Cutoff":
        return "Not good - past cutoff"
    return "Good - within window"

def global_plain_status(booking_role, hold_type, port_data, execution_date, port_check_failed=False):
    good_text = "good to take in" if booking_role == "load_in" else "good"
    not_good_text = "not good to take in" if booking_role == "load_in" else "not good"
    if port_check_failed:
        return f"{not_good_text} - port check failed"
    if hold_type == "Unavailable":
        return f"{not_good_text} - unavailable ({global_unavailable_reason(booking_role, port_data)})"
    if hold_type == "Before ERD":
        return f"{not_good_text} - before ERD for {format_report_date(execution_date)} (ERD {format_report_date(port_data.get('erd_date'))})"
    if hold_type == "Past Cutoff":
        return f"{not_good_text} - past cutoff for {format_report_date(execution_date)} (cutoff {format_report_date(port_data.get('cutoff_date'))})"
    return good_text

def add_global_report_text(key, line):
    if key in global_report_text_seen:
        return
    global_report_text_seen.add(key)
    global_report_text_lines.append(line)

def add_global_report_row(report_rows, booking, execution_date, action, port_data, hold_type, port_check_failed=False, order=None, changes=None, container_override=None, status_override=None, checked_override=None):
    container = ""
    jo = ""
    if order is not None:
        container = clean_port_text(getattr(order, "Container", ""))
        jo = clean_port_text(getattr(order, "Jo", ""))
    if container_override is not None:
        container = clean_port_text(container_override)
    report_rows.append({
        "booking": booking,
        "container": container,
        "jo": jo,
        "execution_date": execution_date,
        "action": action,
        "checked": checked_override if checked_override is not None else "No" if port_check_failed else "Yes",
        "status": status_override if status_override is not None else global_window_status(hold_type, port_check_failed),
        "hold_type": hold_type or "",
        "erd": port_data.get("erd_date") or port_data.get("general_erd") or "",
        "cutoff": port_data.get("cutoff_date") or port_data.get("general_cutoff") or "",
        "shipline": port_data.get("shipline") or "",
        "ship": port_data.get("ship") or "",
        "voyage": port_data.get("voyage") or "",
        "changes": "; ".join(changes or []),
    })

def global_report_table(title, rows):
    headers = ["Booking", "Container", "JO", "In-Gate Date", "Action", "Checked", "Window Status", "Hold", "ERD", "Cutoff", "SSCO", "Ship", "Voyage", "Changes"]
    body = f"<h3>{html.escape(title)}</h3>"
    if not rows:
        return body + "<p>None</p>"
    body += "<table border='1' cellspacing='0' cellpadding='4'><tr>"
    body += "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body += "</tr>"
    for row in rows:
        values = [
            row["booking"], row["container"], row["jo"], format_report_date(row["execution_date"]), row["action"], row["checked"],
            row["status"], row["hold_type"], format_report_date(row["erd"]),
            format_report_date(row["cutoff"]), row["shipline"], row["ship"],
            row["voyage"], row["changes"],
        ]
        body += "<tr>" + "".join(f"<td>{html.escape(str(value or ''))}</td>" for value in values) + "</tr>"
    body += "</table>"
    return body

def send_global_entry_check_report(report_rows):
    execution_dates = sorted({date_value(row["execution_date"]) for row in report_rows if row.get("execution_date")})
    execution_date = execution_dates[0] if execution_dates else latest_global_execution_date or datetime.date.today()
    subject = f"Global Entry Check for Date {format_report_date(execution_date)}"
    body_lines = [f"Global entry check for anticipated in-gate date {format_report_date(execution_date)}.", ""]
    if global_report_text_lines:
        body_lines.extend(global_report_text_lines)
    else:
        body_lines.append("No Global booking checks were recorded.")
    body = "\n".join(body_lines)

    if GLOBAL_TEST_MODE:
        report_path = addpath3(f"emaildocs/global_entry_check_test_{scac}_{format_report_date(execution_date)}.txt")
        with open(report_path, 'w') as f:
            f.write(body)
        print(f"TEST MODE: saved Global entry check report to {report_path}; email will still be sent", flush=True)

    emailfrom = usernames['info']
    emailto = "service@onestoplogisticsco.com"
    username = usernames['info']
    password = passwords['info']

    msg = MIMEMultipart()
    msg["From"] = emailfrom
    msg["To"] = emailto
    msg["Subject"] = subject
    msg.attach(MIMEText(body, 'plain'))

    print(f"Attempting to send Global entry check report to {emailto} with subject: {subject}", flush=True)
    server = smtplib.SMTP(websites['mailserver'])
    server.starttls()
    server.login(username, password)
    server.sendmail(emailfrom, [emailto], msg.as_string())
    server.quit()
    print(f"Sent Global entry check report to {emailto} with subject: {subject}", flush=True)

def global_email_marker_path():
    return addpath3(f'emaildocs/global_latest_processed_{scac}.txt')

def global_email_marker(data):
    msg_id = get_message_id(data)
    msg_dt = get_datetime(data)
    subject = get_subject(data)
    dt_text = msg_dt.isoformat() if msg_dt is not None else ''
    if msg_id:
        return msg_id
    return f"{dt_text}|{clean_port_text(subject)}"

def read_global_processed_marker():
    try:
        with open(global_email_marker_path()) as f:
            return f.read().strip()
    except:
        return ''

def write_global_processed_marker(marker):
    with open(global_email_marker_path(), 'w') as f:
        f.write(marker)

def decode_global_body(body):
    if isinstance(body, str):
        return body
    for encoding in ('utf-8', 'windows-1252', 'latin-1'):
        try:
            return body.decode(encoding)
        except:
            pass
    return body.decode('utf-8', errors='replace')

def html_body_to_text(body):
    body = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", body)
    body = re.sub(r"(?i)</\s*(p|div|tr|li|h[1-6])\s*>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    return html.unescape(body)

def decode_message_part(part):
    payload = part.get_payload(decode=True)
    if payload is None:
        payload = part.get_payload()
    return decode_global_body(payload)

def get_global_message_text(raw_msg):
    plain_parts = []
    html_parts = []
    if raw_msg.is_multipart():
        for part in raw_msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is not None:
                continue
            content_type = part.get_content_type()
            try:
                text = decode_message_part(part)
            except:
                continue
            if content_type == 'text/plain':
                plain_parts.append(text)
            elif content_type == 'text/html':
                html_parts.append(html_body_to_text(text))
    else:
        text = decode_message_part(raw_msg)
        if raw_msg.get_content_type() == 'text/html':
            html_parts.append(html_body_to_text(text))
        else:
            plain_parts.append(text)

    if plain_parts:
        return "\n".join(plain_parts)
    return "\n".join(html_parts)

def line_size(line):
    if "20'" in line:
        return "20"
    if "45'" in line:
        return "45"
    return "40"

def global_line_role(line):
    line_l = line.lower()
    if "container" in line_l or container_p.search(line):
        return "load_in"
    if "bring back" in line_l:
        return "empty_out"
    return "booking"

def combine_global_roles(old_role, new_role):
    if old_role == new_role:
        return old_role
    if old_role == "mixed" or new_role == "mixed":
        return "mixed"
    if old_role in ("load_in", "empty_out") and new_role in ("load_in", "empty_out"):
        return "mixed"
    return new_role if old_role == "booking" else old_role

def global_hstat1_order_by_booking(booking):
    return Orders.query.filter(
        (Orders.Shipper == 'Global Business Link') &
        (Orders.Hstat == 1) &
        ((Orders.Booking == booking) | (Orders.BOL == booking))
    ).order_by(Orders.id.desc()).first()

def global_order_by_booking(booking):
    return Orders.query.filter(
        (Orders.Shipper == 'Global Business Link') &
        ((Orders.Booking == booking) | (Orders.BOL == booking))
    ).order_by(Orders.id.desc()).first()

def global_order_by_container(container):
    return Orders.query.filter(
        (Orders.Shipper == 'Global Business Link') &
        (Orders.Container == container)
    ).order_by(Orders.id.desc()).first()

def is_completed_global_order(order):
    try:
        return order is not None and order.Hstat is not None and int(order.Hstat) > 1
    except:
        return False

def global_hstat1_order_by_container(container):
    return Orders.query.filter(
        (Orders.Shipper == 'Global Business Link') &
        (Orders.Hstat == 1) &
        (Orders.Container == container)
    ).order_by(Orders.id.desc()).first()

def resolve_global_load_container(booking, container, execution_date, report_rows):
    if container:
        any_order = global_order_by_container(container)
        if is_completed_global_order(any_order):
            print(f"Skipping Global load line for completed container {container} with Hstat {any_order.Hstat}", flush=True)
            return None
        order = global_hstat1_order_by_container(container)
        if order is None:
            add_global_report_row(
                report_rows, booking, execution_date, "Load Container Issue",
                default_global_port_data(), None, checked_override="No",
                status_override="Issue - container not found at Hstat 1",
                changes=[f"Email container {container} not found on Global Hstat 1 order"],
                container_override=container,
            )
            return None
        order_booking = clean_port_text(order.Booking)
        order_bol = clean_port_text(order.BOL)
        if booking not in (order_booking, order_bol):
            add_global_report_row(
                report_rows, booking, execution_date, "Load Container Issue",
                default_global_port_data(), None, checked_override="No",
                status_override="Issue - booking/container mismatch",
                order=order,
                changes=[f"Email booking {booking} does not match order Booking {order_booking} or BOL {order_bol}"],
            )
            return None
        return container

    any_order = global_order_by_booking(booking)
    if is_completed_global_order(any_order):
        print(f"Skipping Global unknown-container line for completed booking {booking} with Hstat {any_order.Hstat}", flush=True)
        return None

    order = global_hstat1_order_by_booking(booking)
    if order is None or not clean_port_text(order.Container):
        add_global_report_row(
            report_rows, booking, execution_date, "Load Container Issue",
            default_global_port_data(), None, checked_override="No",
            status_override="Issue - unknown container not resolved",
            changes=[f"No Global Hstat 1 order with container found for booking {booking}"],
        )
        return None

    resolved = clean_port_text(order.Container).upper()
    add_global_report_row(
        report_rows, booking, execution_date, "Load Container Resolved",
        default_global_port_data(), None, checked_override="No",
        status_override="Resolved unknown container from database",
        order=order,
        changes=[f"Unknown container resolved to {resolved}"],
        container_override=resolved,
    )
    return resolved

def collect_global_pin_pairs(bodylines, email_date, report_rows=None):
    if report_rows is None:
        report_rows = []
    pairs = []
    load_queue = []
    execution_date = next_global_execution_date(email_date)
    for line in bodylines:
        bookings = get_bookings(line)
        if not bookings:
            continue
        containers = [container.upper().strip() for container in container_p.findall(line)]
        is_load_line = bool(containers) or "container" in line.lower()
        if is_load_line:
            for booking in bookings:
                container = containers[0] if containers else None
                container = resolve_global_load_container(booking, container, execution_date, report_rows)
                if container is None:
                    continue
                load_queue.append({
                    "booking": booking,
                    "container": container,
                    "size": line_size(line),
                    "execution_date": execution_date,
                })
        else:
            for booking in bookings:
                if not load_queue:
                    continue
                load = load_queue.pop(0)
                pairs.append({
                    "inbook": load["booking"],
                    "incon": load["container"],
                    "size": load["size"],
                    "outbook": booking,
                    "execution_date": execution_date,
                })
    return pairs

def global_port_review(cache, booking, execution_date, label):
    key = (booking, execution_date)
    if key in cache:
        return cache[key]

    port_data = default_global_port_data()
    port_check_failed = False
    try:
        port_data = get_global_booking_port_data(booking)
        print(
            f"{label} {booking} port check: total={port_data['total']} "
            f"received={port_data['received']} delivered={port_data['delivered']} valid={port_data['valid']} "
            f"ERD={port_data['general_erd']} cutoff={port_data['general_cutoff']}",
            flush=True,
        )
    except Exception as exc:
        port_check_failed = True
        print(f"{label} {booking} port check failed: {exc}", flush=True)

    hold_type = global_booking_hold_type(port_data, execution_date, port_check_failed)
    cache[key] = (port_data, port_check_failed, hold_type)
    return cache[key]

def collect_global_latest_report_text(bodylines, email_date):
    execution_date = next_global_execution_date(email_date)
    port_cache = {}
    for line in bodylines:
        bookings = get_bookings(line)
        if not bookings:
            continue
        role = global_line_role(line)
        if role not in ("load_in", "empty_out"):
            continue
        containers = [container.upper().strip() for container in container_p.findall(line)]
        for booking in bookings:
            try:
                port_data, port_check_failed, hold_type = global_port_review(
                    port_cache, booking, execution_date, "Global latest email booking"
                )
            except Exception as exc:
                port_data = default_global_port_data()
                port_check_failed = True
                hold_type = "Unavailable"
                print(f"Global latest email booking {booking} report check failed: {exc}", flush=True)
            if role == "load_in":
                hold_type = global_load_in_hold_type(port_data, execution_date, port_check_failed)
                container = containers[0] if containers else ""
                if not container:
                    order = global_order_by_booking(booking)
                    container = clean_port_text(getattr(order, "Container", ""))
                status_text = global_plain_status(role, hold_type, port_data, execution_date, port_check_failed)
                add_global_report_text(
                    ("load_in", booking, container, execution_date),
                    f"Load-in {booking} container {container or 'unknown'}: {status_text}."
                )
            else:
                hold_type = global_empty_out_hold_type(port_data, execution_date, port_check_failed)
                status_text = global_plain_status(role, hold_type, port_data, execution_date, port_check_failed)
                add_global_report_text(
                    ("new_booking", booking, execution_date),
                    f"New booking {booking}: {status_text}."
                )

def global_pin_queue_exists(incon, outbook, execution_date):
    return Pins.query.filter(
        (Pins.InCon == incon) &
        (Pins.OutBook == outbook) &
        (Pins.Date == execution_date)
    ).first() is not None

def create_global_pin_queue_rows(pin_pairs, report_rows):
    if not pin_pairs:
        return

    port_cache = {}
    for pair in pin_pairs:
        execution_date = pair["execution_date"]
        inbook = pair["inbook"]
        outbook = pair["outbook"]
        incon = pair["incon"]
        if execution_date < datetime.date.today():
            continue

        in_port_data, in_failed, in_hold = global_port_review(port_cache, inbook, execution_date, "Global load-in booking")
        in_hold = global_load_in_hold_type(in_port_data, execution_date, in_failed)
        add_global_report_row(
            report_rows, inbook, execution_date, "Pin Queue Load In Check",
            in_port_data, in_hold, in_failed,
            changes=[f"Matched empty-out {outbook}", global_unavailable_reason("load_in", in_port_data)],
            container_override=incon,
        )
        if in_hold is not None:
            print(f"Skipping Global pin queue for load-in {inbook} {incon}: {global_window_status(in_hold, in_failed)}", flush=True)
            continue

        out_port_data, out_failed, out_hold = global_port_review(port_cache, outbook, execution_date, "Global empty-out booking")
        out_hold = global_empty_out_hold_type(out_port_data, execution_date, out_failed)
        add_global_report_row(
            report_rows, outbook, execution_date, "Pin Queue Empty Out Check",
            out_port_data, out_hold, out_failed,
            changes=[f"Matched load-in {inbook} {incon}", global_unavailable_reason("empty_out", out_port_data)],
        )
        if out_hold is not None:
            print(f"Skipping Global pin queue for empty-out {outbook}: {global_window_status(out_hold, out_failed)}", flush=True)
            continue

        if global_pin_queue_exists(incon, outbook, execution_date):
            print(f"Global pin queue already has {incon} with empty-out {outbook} for {execution_date}", flush=True)
            continue

        idat = Interchange.query.filter(Interchange.Release == inbook).order_by(Interchange.id.desc()).first()
        inchas = idat.Chassis if idat is not None else None
        intext = f"Load In: *{inbook} {incon}* (Global {pair['size']} customs)"
        outtext = f"Empty Out: *{outbook}* (Global {pair['size']})"
        pin = Pins(Date=execution_date, Driver=None, InBook=inbook, InCon=incon, InChas=inchas,
                   InPin='0', OutBook=outbook, OutCon=None, OutChas=inchas, OutPin='0',
                   Unit=None, Tag=None, Phone=None, Intext=intext, Outtext=outtext,
                   Notes='Created by FFF_emailread_daily Global booking check', Timeslot=0, Active=0, Maker='Web')
        db.session.add(pin)
        db.session.commit()
        add_global_report_row(
            report_rows, inbook, execution_date, "Pin Queue Added",
            in_port_data, in_hold, in_failed,
            changes=[f"OutBook {outbook}", f"InCon {incon}", f"InChas {inchas or ''}"],
            container_override=incon,
        )
        print(f"Added Global pin queue row for load-in {inbook} {incon} with empty-out {outbook}", flush=True)

if 1==1:

    if remit>0:

        msgs=get_emails(search('FROM','ReportServer@KnightTrans.com',con),con)
        att_dir='/home/mark/alldocs/emailextracted/knightremits'
        for j,msg in enumerate(msgs):
            adder=datename(msg)
            #print(adder)
            this_name='Remittance'+'_'+adder+'.pdf'
            #print(get_body(email.message_from_bytes(msg[0][1])))
            raw=email.message_from_bytes(msg[0][1])
            get_attachments_name(raw,this_name,att_dir)

        for file2 in os.listdir(att_dir):
            if fnmatch.fnmatch(file2, '*.pdf'):
                #Check to see if already in database:
                base=os.path.splitext(file2)[0]
                tp=subprocess.check_output(['pdf2txt.py', '-o', os.path.join(att_dir,base+'.txt'), os.path.join(att_dir,file2)])



#_____________________________________________________________________________________________________________
# Subroutine to grab bookings from ABE for Global work and put into the database on website
#_____________________________________________________________________________________________________________
    if gjob>0:
        if gjob==1:
            dayback=5
        if gjob==2:
            dayback=450
        datefrom = (datetime.date.today() - datetime.timedelta(dayback)).strftime("%d-%b-%Y")
        #print(datefrom)
        username = usernames['infh']
        password = passwords['infh']
        con = imaplib.IMAP4_SSL(imap_url)
        con.login(username,password)
        con.select('INBOX')
        msgs=get_emails(search_from_date('FROM','@gblna.com',con,datefrom),con)
        # msgs=get_emails(search('FROM','aalsawi@gblna.com',con),con)
        con.close()
        con.logout()

        latest_global_msg = None
        latest_global_dt = None
        latest_global_email_date = None
        latest_global_execution_date = None
        latest_global_index = None
        latest_global_roles = {}
        global_pin_pairs = []
        if gjob==1 and msgs:
            for idx,msg in enumerate(msgs):
                msg_dt = get_datetime(msg)
                if msg_dt is not None and (latest_global_dt is None or msg_dt > latest_global_dt):
                    latest_global_dt = msg_dt
                    latest_global_msg = msg
                    latest_global_index = idx
            if latest_global_msg is not None:
                latest_global_marker = global_email_marker(latest_global_msg)
                latest_global_email_date = latest_global_dt.date()
                latest_global_execution_date = next_global_execution_date(latest_global_dt.date())
                process_latest_global_ops = GLOBAL_TEST_MODE or latest_global_marker != read_global_processed_marker()
                if process_latest_global_ops:
                    print(f"Latest Global email will be used for report and pin queue: {latest_global_marker}", flush=True)
                else:
                    print(f"Latest Global email already processed for report and pin queue: {latest_global_marker}", flush=True)
                if process_latest_global_ops:
                    try:
                        latest_raw = email.message_from_bytes(latest_global_msg[0][1])
                        latest_body = get_global_message_text(latest_raw)
                        latest_lines = latest_body.splitlines()
                        print(
                            f"Latest Global email report parser saw {len(latest_lines)} line(s) "
                            f"and {len(get_bookings(latest_body))} booking token(s)",
                            flush=True,
                        )
                        for latest_booking in get_bookings(latest_body):
                            latest_global_roles[latest_booking] = global_booking_role_from_lines(latest_booking, latest_lines)[0]
                        global_pin_pairs.extend(collect_global_pin_pairs(latest_lines, latest_global_dt.date(), global_report_rows))
                        print(f"Collected {len(global_pin_pairs)} Global pin pair candidate(s) from latest email", flush=True)
                    except Exception as exc:
                        print(f"Could not collect Global pin pair candidates from latest email: {exc}", flush=True)

        bookings=[]
        norepeat=[]
        for j,msg in enumerate(msgs):
            raw=email.message_from_bytes(msg[0][1])
            body=get_global_message_text(raw)
            getdate=get_date(msg)
            if 1 == 1:
                try:
                    body=decode_global_body(body)
                    skipit = 1
                except:
                    #print(f'body not decoded:{body}')
                    skipit = 0
                if skipit:
                    blist=get_bookings(body)
                    bodylines = body.splitlines()
                    apply_latest_ops = process_latest_global_ops and j == latest_global_index
                    if apply_latest_ops:
                        print(f"Parsing latest Global email for report and pin queue: {latest_global_marker}", flush=True)
                    if blist:
                        #print(f'{getdate} {blist}')
                        for b in blist:
                            b=normalize_booking(b)
                            booking_role, size = global_booking_role_from_lines(b, bodylines)
                            if b not in norepeat:
                                booktriplet=[b,getdate,getdate,size,apply_latest_ops,booking_role]
                                bookings.append(booktriplet)
                                norepeat.append(b)
                                if apply_latest_ops:
                                    print(f"Latest Global booking {b} role={booking_role} execution_date={next_global_execution_date(getdate)}", flush=True)
                            else:
                            #find the existing booking and replace the second date
                                for book in bookings:
                                    if book[0]==b:
                                        book[2]=getdate
                                        if apply_latest_ops:
                                            book[1]=getdate
                                            book[4]=True
                                            print(f"Latest Global booking {b} role={booking_role} execution_date={next_global_execution_date(getdate)}", flush=True)
                                        book[5]=combine_global_roles(book[5], booking_role)

                else:
                    print('Bad decode on',getdate)


        try:
            with open(addpath3(f'emaildocs/global_jobs_{scac}.txt')) as f:
                longs=f.read()
            f.close()
        except:
            longs=''

        if gjob==1:
            ot='a'
        if gjob==2:
            ot='w'

        with open(addpath3(f'emaildocs/global_jobs_{scac}.txt'),ot) as f:
            for book in bookings:
                b=book[0]
                d1=book[1].strftime('%Y-%m-%d')
                d2=book[2].strftime('%Y-%m-%d')
                latest_email_booking = (
                    process_latest_global_ops and
                    latest_global_email_date is not None and
                    book[2] == latest_global_email_date
                )
                execution_date = latest_global_execution_date if latest_email_booking else next_global_execution_date(book[1])
                apply_latest_ops = gjob==1 and len(book) > 4 and book[4]
                booking_role = book[5] if len(book) > 5 else 'booking'
                report_latest_booking = latest_email_booking
                if report_latest_booking and b in latest_global_roles:
                    booking_role = latest_global_roles[b]
                pulldate = execution_date
                indate = execution_date
                try:
                    size = book[3]
                except:
                    size = '40'
                if gjob==2:
                    #print('Adding',b,d1,d2)
                    f.write(b+' '+d1+' '+d2+'\n')

                if gjob==1:
                    bdat=global_order_by_booking(b)
                    if is_completed_global_order(bdat):
                        print(f'                Skipping completed Global booking {b} with Hstat {bdat.Hstat}')
                        continue
                    pdat = People.query.filter(People.Company == 'Global Business Link').first()
                    bid = pdat.id
                    ldat = Drops.query.filter(Drops.Entity == 'Global Business Link').first()
                    lid = ldat.id
                    ddat = Drops.query.filter(Drops.Entity == 'Baltimore Seagirt').first()
                    did = ddat.id
                    if size == '40': putsize = '''40' GP 9'6"'''
                    if size == '20': putsize = '''20' GP 8'6"'''
                    port_data = default_global_port_data()
                    port_check_failed = False
                    should_create_order = bdat is None
                    should_review_port = should_create_order or report_latest_booking
                    if should_review_port:
                        report_role = global_effective_report_role(booking_role, bdat)
                        port_check_failed = False
                        try:
                            port_data = get_global_booking_port_data(b)
                            print(
                                f"Global booking {b} port check ({report_role}): total={port_data['total']} "
                                f"received={port_data['received']} delivered={port_data['delivered']} "
                                f"ERD={port_data['general_erd']} cutoff={port_data['general_cutoff']}",
                                flush=True,
                            )
                        except Exception as exc:
                            port_check_failed = True
                            print(f"Global booking {b} port booking availability check failed; creating order with HoldType Unavailable: {exc}", flush=True)

                        if report_role == "load_in":
                            hold_type = global_load_in_hold_type(port_data, execution_date, port_check_failed)
                        elif report_role == "empty_out":
                            hold_type = global_empty_out_hold_type(port_data, execution_date, port_check_failed)
                        else:
                            hold_type = global_booking_hold_type(port_data, execution_date, port_check_failed)
                        if gjob == 1 and process_latest_global_ops:
                            status_text = global_plain_status(report_role, hold_type, port_data, execution_date, port_check_failed)
                            if report_role == "load_in":
                                container_text = clean_port_text(getattr(bdat, "Container", "")) if bdat is not None else ""
                                add_global_report_text(
                                    ("checked_load_in", b, container_text, execution_date),
                                    f"Load-in {b} container {container_text or 'unknown'}: {status_text}."
                                )
                            else:
                                label = "New booking" if bdat is None else "Booking"
                                add_global_report_text(
                                    ("checked_booking", b, execution_date),
                                    f"{label} {b}: {status_text}."
                                )
                        if not port_check_failed and hold_type == "Unavailable":
                            print(
                                f"Global booking {b} is not currently available; using HoldType Unavailable "
                                f"({global_unavailable_reason(report_role, port_data)})",
                                flush=True,
                            )
                        if hold_type in ("Before ERD", "Past Cutoff"):
                            print(
                                f"Global booking {b} execution date {execution_date} is outside port window "
                                f"ERD={port_data['erd_date']} cutoff={port_data['cutoff_date']}; "
                                f"using HoldType {hold_type}",
                                flush=True,
                            )

                    if bdat is not None:
                        if should_review_port:
                            changes, hold_type = update_global_order_from_port(bdat, port_data, execution_date, port_check_failed, hold_type)
                            if apply_latest_ops or report_latest_booking:
                                add_global_report_row(
                                    global_report_rows, b, execution_date, "Updated" if changes else "Existing",
                                    port_data, hold_type, port_check_failed, bdat, changes,
                                )
                            if changes:
                                print(f"Updated existing Global booking {b}: {'; '.join(changes)}", flush=True)
                                db.session.commit()
                        print(f'                Skipping creation for existing Global booking {book[0]} {book[1]} {book[2]}')

                    elif should_create_order:
                        if booking_role == 'load_in':
                            hold_type = global_load_in_hold_type(port_data, execution_date, port_check_failed)
                        elif booking_role == 'empty_out':
                            hold_type = global_empty_out_hold_type(port_data, execution_date, port_check_failed)
                        else:
                            hold_type = global_booking_hold_type(port_data, execution_date, port_check_failed)

                        if b not in longs:
                            f.write(b+' '+d1+' '+d2+'\n')
                        sdate=getdate.strftime('%Y-%m-%d')
                        jtype=tcode + 'T'
                        nextjo=newjo(jtype,sdate)
                        load='G'+nextjo[-5:]
                        order=plan_order_value(pulldate)
                        #print(doc)
                        erd_date = port_data["erd_date"]
                        cutoff_date = port_data["cutoff_date"]

                        input = Orders(Status='AO', Jo=nextjo, HaulType='Dray Export DP', Order=order, Bid=bid, Lid=lid,
                                       Did=did, Company2='Global Business Link', Location=None, BOL=None, Booking=b,
                                       Container=None, Driver=None, Pickup=None, Delivery=None, Amount='370.00',
                                       Date=pulldate, Time=None, Time3=None, Date2=indate, Time2=None, PaidInvoice=None,
                                       Source=None, Description=None, Chassis=None, Detention=None,
                                       Storage=None, Release=0, Company='Baltimore Seagirt', Seal=None,
                                       Shipper='Global Business Link', Type=putsize, Label=None,
                                       Dropblock2='Global Business Link\n4000 Coolidge Ave K\nBaltimore, MD 21229',
                                       Dropblock1='Baltimore Seagirt\n2600 Broening Hwy\nBaltimore, MD 21224',
                                       Commodity=None, Packing=None, Links=None, Hstat=-1, Istat=-1, Proof='No Proof Needed',
                                       Invoice=None, Gate=None, Package=None, Manifest=None, Scache=0, Pcache=0,
                                       Icache=0, Mcache=0, Pkcache=0, QBi=None, InvoTotal='370.00', Truck=None,
                                       Dropblock3=None, Date3=pulldate, Location3=None, InvoDate=None, PaidDate=None,
                                       PaidAmt=None, PayRef=None, PayMeth=None, PayAcct=None, BalDue=None, Payments=None, Quote=None,
                                       Date4=erd_date,Date5=cutoff_date,Date6=None,RateCon=None,Rcache=0,Proof2=None,Pcache2=0,Emailjp=None,
                                       Emailoa=None,Emailap=None,Saljp=None,Saloa=None,Salap=None,Date7=None,SSCO=port_data["shipline"],Date8=indate,Ship=port_data["ship"],Voyage=port_data["voyage"],
                                       UserMod='FFF_emailread_daily', DelStat=0, DrvProof=None, DrvSeal=None, D1cache=0, D2cache=0,
                                       HoldType=hold_type)


                        db.session.add(input)
                        db.session.commit()
                        if apply_latest_ops or report_latest_booking:
                            add_global_report_row(
                                global_report_rows, b, execution_date, "Added",
                                port_data, hold_type, port_check_failed, input,
                            )
                    else:
                        print(f'                Skipping Global booking {book[0]} {book[1]} {book[2]} because no create/update condition matched')

        if gjob==1:
            create_global_pin_queue_rows(global_pin_pairs, global_report_rows)

today = datetime.date.today()
cutoffdate = today - datetime.timedelta(120)
######Change booking of job for container if pulled under different booking#####
cdata = Orders.query.filter( (Orders.Shipper == 'Global Business Link') & (Orders.Hstat == 2) & (Orders.Istat < 3) & (Orders.Date > cutoffdate) ).all()
for cdat in cdata:
    bk = cdat.Booking
    con = cdat.Container
    jo = cdat.Jo
    idata = Interchange.query.filter( (Interchange.Container == con) & (Interchange.Date > cutoffdate) ).all()
    #print(bk, con, len(idata))
    if len(idata) == 2:
        idat1 = idata[0]
        idat2 = idata[1]
        type1 = idat1.Type
        type2 = idat2.Type
        bkin = None
        bkout = None
        if type1 == 'Load In':
            bkin = idat1.Release
            bkout = idat2.Release
        elif type1 == 'Empty Out':
            bkin = idat2.Release
            bkout = idat1.Release
        elif type1 == 'Dray Off':
            bkin = idat2.Release
            bkout = idat1.Release


        if bkin is None or bkout is None:
            print(f'For container {con} could not determine in/out bookings from interchange types {type1} and {type2}')
        elif bkin == bkout:
            print(f'For container {con} the bookings match out and in')
        else:
            print(f'For container {con} the bookings match out and in do not match')
            if cdat.BOL is None:
                print(f'For container {con} the in booking set to {bkin}')
                cdat.BOL = bkin
                db.session.commit()
            else:
                if cdat.Booking != bkout or cdat.BOL != bkin:
                    print(f'For container {con} the out on {bkout} and in on {bkin}')
                    cdat.Booking = bkout
                    cdat.BOL = bkin
                    db.session.commit()

        should_report_container_check = (
            process_latest_global_ops and
            latest_global_execution_date is not None and
            (date_value(cdat.Date2) or date_value(cdat.Date) or today) == latest_global_execution_date
        )

        if bkin is not None and should_report_container_check:
            in_booking = normalize_booking(str(bkin))
            execution_date = latest_global_execution_date
            port_data = default_global_port_data()
            port_check_failed = False
            try:
                port_data = get_global_booking_port_data(in_booking)
                print(
                    f"Global container {con} in-booking {in_booking} port check: total={port_data['total']} "
                    f"received={port_data['received']} delivered={port_data['delivered']} valid={port_data['valid']} "
                    f"ERD={port_data['general_erd']} cutoff={port_data['general_cutoff']}",
                    flush=True,
                )
            except Exception as exc:
                port_check_failed = True
                print(f"Global container {con} in-booking {in_booking} port check failed; using HoldType Unavailable: {exc}", flush=True)

            hold_type = global_load_in_hold_type(port_data, execution_date, port_check_failed)
            if not port_check_failed and hold_type == "Unavailable":
                print(
                    f"Global container {con} in-booking {in_booking} is not currently available "
                    f"({global_unavailable_reason('load_in', port_data)})",
                    flush=True,
                )

            changes, hold_type = update_global_order_from_port(cdat, port_data, execution_date, port_check_failed, hold_type)
            add_global_report_row(
                global_report_rows, in_booking, execution_date, "Container In-Book",
                port_data, hold_type, port_check_failed, cdat, changes,
            )
            if changes:
                print(f"Updated Global container {con} from in-booking {in_booking}: {'; '.join(changes)}", flush=True)
                db.session.commit()




#####Now kill Global Bookings placed in system that are over 8 days old...unlikely to be used.
kdata = Orders.query.filter( (Orders.Shipper == 'Global Business Link') & (Orders.Hstat <= 0)).all()
ksid = []
isid = []

for kdat in kdata:
    kdate = kdat.Date
    daysover = today - kdate
    daysover = daysover.days
    if daysover > 12:
        #print(f'For JO {kdat.Jo} with booking {kdat.Booking} and Hstat {kdat.Hstat} from {kdate} to {today} no pull for {daysover} days')
        check = Interchange.query.filter( (Interchange.Release == kdat.Booking) & (Interchange.Date > cutoffdate) ).all()
        if check != []:
            #print(f'Found a booking pulled {kdat.Booking} with no match in the orders for Global')
            isid.append(kdat.id)
            #for ck in check:
                #print(f'Found Interchange for {ck.Release} and {ck.Container}')
        else:
            #print(f'Confirmed for Killing booking {kdat.Booking} from {kdat.Date} to {today} no pull for {daysover} days')
            ksid.append(kdat.id)

#print(f'Killing these jobs : {ksid}')
#print(f'Need to investigate: {isid}')
for ki in ksid:
    Orders.query.filter(Orders.id == ki).delete()
db.session.commit()



if gjob==1:
    try:
        print(f"Preparing Global entry check report with {len(global_report_text_lines)} text line(s)", flush=True)
        send_global_entry_check_report(global_report_rows)
        if process_latest_global_ops and latest_global_marker and not GLOBAL_TEST_MODE:
            write_global_processed_marker(latest_global_marker)
    except Exception as exc:
        print(f"Could not send Global entry check report: {exc}", flush=True)
close_booking_review_browser()
if nt == 'remote': tunnel.stop()
