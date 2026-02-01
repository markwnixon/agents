import os
import sys

import socket
from utils import getpaths

import time
from datetime import datetime, timedelta
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import *
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from utils import hasinput
from selenium.webdriver.firefox.options import Options
import logging

logger = logging.getLogger()  # root logger
logger.setLevel(logging.DEBUG)

# create file handler
fh = logging.FileHandler('/home/mark/selenium_debug.log')
fh.setLevel(logging.DEBUG)

# create formatter and attach
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)

# attach handler to logger
logger.addHandler(fh)
logger.debug("Logging initialized")

try:
    scac = sys.argv[1]
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    quit()

try:
    pinid = sys.argv[2]
    pinid = int(pinid)
    print(f'Received input argument of pinid: {pinid}')
except:
    print('Must have a pinid argument')
    quit()

nt = 'remote'
po = True
scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running FFF_make_pins_headless for {scac} for pinid {pinid} in tunnel mode: {nt}')
    host_name = socket.gethostname()
    print("Host Name:", host_name)
    dropbox_path = getpaths(host_name, 'dropbox')
    ar_path = f'{dropbox_path}/Dray/{scac}_AR_Report.xlsx'
    sys_path = getpaths(host_name, 'system')
    sys.path.append(sys_path) #So we can import CCC_system_setup from full path

    os.environ['SCAC'] = scac
    os.environ['PURPOSE'] = 'script'
    os.environ['MACHINE'] = host_name
    os.environ['TUNNEL'] = nt

    from remote_db_connect import db
    if nt == 'remote': from remote_db_connect import tunnel
    from models8 import Interchange, Orders, Drivers, Pins
    from CCC_system_setup import websites, usernames, passwords

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

printif = 0
runat = datetime.now()
tnow = runat.strftime("%M")
mins = int(tnow)
today = runat.date()
textblock = f'This sequence run at {runat} and minutes are {mins}\n'

def closethepopup(browser, close_button_xpath, timeout=10):
    wait = WebDriverWait(browser, timeout)

    wait.until(EC.presence_of_element_located((By.XPATH, close_button_xpath)))

    for _ in range(3):
        try:
            for btn in browser.find_elements(By.XPATH, close_button_xpath):
                if btn.is_displayed() and "close" in btn.text.lower():
                    browser.execute_script("arguments[0].click();", btn)
                    return True
        except StaleElementReferenceException:
            pass

    return False

def softwait(browser, xpath, timeout=16):
    try:
        wait = WebDriverWait(browser, timeout, poll_frequency=0.5)
        return wait.until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )
    except TimeoutException:
        print(f"Timed out waiting for element: {xpath}")
        return None

def softwait_long(browser, xpath, timeout=30):
    """
    Waits for a toast/message to become visible again.
    Works for repeated PrimeFaces-style messages.
    """
    end_time = time.time() + timeout

    while time.time() < end_time:
        elements = browser.find_elements(By.XPATH, xpath)
        for el in elements:
            if el.is_displayed() and el.text.strip():
                return el
        time.sleep(0.25)

    print("Timeout waiting for toast to reappear")
    return None


def hard_select_option(browser, select_id, option_text, timeout=20, retries=3):
    """
    Headless-safe hard select:
    - waits for enabled
    - re-finds element every attempt
    - sets value via JS
    - fires change/input events
    """

    for attempt in range(1, retries + 1):
        print(f'Hard selection attempt {attempt}')

        try:
            # Wait for element to exist
            WebDriverWait(browser, timeout).until(
                EC.presence_of_element_located((By.ID, select_id))
            )

            selectElem = browser.find_element(By.ID, select_id)

            # Wait until enabled (checkbox JS often toggles this)
            WebDriverWait(browser, timeout).until(
                lambda d: selectElem.is_enabled()
            )

            # Scroll + focus
            browser.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();",
                selectElem
            )

            # Try normal Select first
            try:
                Select(selectElem).select_by_visible_text(option_text)
            except Exception:
                pass  # fallback to JS below

            # 🔥 Force JS value + events (headless critical)
            browser.execute_script("""
                const sel = arguments[0];
                const text = arguments[1];
                const opts = [...sel.options];
                const opt = opts.find(o => o.text.trim() === text);

                if (!opt) throw "Option not found";

                sel.value = opt.value;
                sel.dispatchEvent(new Event('input', { bubbles: true }));
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            """, selectElem, option_text)

            # Confirm selection stuck
            WebDriverWait(browser, timeout).until(
                lambda d: Select(d.find_element(By.ID, select_id))
                          .first_selected_option.text.strip() == option_text
            )

            return  # success

        except (StaleElementReferenceException, TimeoutException) as e:
            time.sleep(0.3)

    raise Exception(f"Failed to hard-select '{option_text}' in select '{select_id}'")


def get_text(browser, xpath):
    time.sleep(1)
    textboxes = browser.find_elements_by_xpath(xpath)
    time.sleep(1)
    print(f'The textboxes for xpath {xpath} is {textboxes}')
    ret_text = 'xxxxx'
    if textboxes:
        for textbox in textboxes:
            thistext = textbox.text
            print(f'Finding textboxes on page: {thistext}')
            if 'Pre-Advise PIN' in thistext: ret_text = thistext
    else:
        ret_text = 'No textboxes found'
    return ret_text

def get_result_message(browser, timeout=15):
    """
    Returns success PIN message or error dialog text.
    """
    error = 0

    wait = WebDriverWait(browser, timeout)

    # XPaths
    success_xpath = "//*[contains(text(),'Pre-Advise created successfully')]"
    error_xpath = "//div[contains(@class,'ui-dialog-content')]//td[contains(@class,'error')]"
    # NEW: alert dialog without td.error
    alert_xpath = "//div[@id='dialog-alert']//td[normalize-space()]"

    try:
        elem = wait.until(
            lambda d: next(
                (
                    e for e in
                    d.find_elements(By.XPATH, success_xpath)
                    + d.find_elements(By.XPATH, error_xpath)
                    + d.find_elements(By.XPATH, alert_xpath)
                    if e.is_displayed() and e.text.strip()
                ),
                None
            )
        )

        text = elem.text.strip()
        print(f"Popup message found: {text}")

        if 'successfully' in text:
            error = False
        else: error = True

        return text, error

    except TimeoutException:
        return "No result message found", True

# Wait until the select has more than 1 option (skip placeholder 'Loading...')
def wait_for_timeslots(browser, xpath, timeout=20):

    def options_populated(driver):
        sel = driver.find_element(By.XPATH, xpath)
        return len(sel.find_elements(By.TAG_NAME, "option")) > 1  # >1 to skip placeholder

    return WebDriverWait(browser, timeout).until(options_populated)

def Waitpageloadcomplete(browser):
    # Once the xpaths for elements at the start and end of form appear, we wait
    # for the page load to complete:

    WebDriverWait(browser, 20).until(
        lambda d: d.execute_script(
            "return window.jQuery !== undefined && jQuery.active === 0"
        )
    )


def type_entry(browser, xp, text, ending):
    print(f'Typing into xpath {xp} the text {text}')

    elem = WebDriverWait(browser, 10).until(
        lambda d: d.find_element(By.XPATH, xp)
    )

    elem.click()

    # Wait until browser confirms focus
    WebDriverWait(browser, 5).until(
        lambda d: d.execute_script("return document.activeElement === arguments[0];", elem)
    )

    for ch in text:
        elem.send_keys(ch)
        time.sleep(0.08)

    if ending == 'TAB':
        elem.send_keys(Keys.TAB)
    elif ending == 'ENTER':
        elem.send_keys(Keys.ENTER)


def fillapptdata(browser, d, p, thisdate):

    print(f'This date is {thisdate}')

    if 1 == 2:
        softwait(browser, '//*[@id="DualInfo_NewApptDate"]')
        selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_NewApptDate"]')
        selectElem.send_keys(thisdate)
        selectElem.submit()
    softwait(browser, '//*[@id="DualInfo_NewApptDate"]')
    dateElem = browser.find_element_by_id("DualInfo_NewApptDate")
    dateElem.click()
    browser.execute_script("arguments[0].focus();", dateElem)
    for ch in thisdate:
        dateElem.send_keys(ch)
        time.sleep(0.08)
    dateElem.send_keys(Keys.TAB)

    #after date submit the timeslot becomes populated but lets wait for the page to finish loading first

    timedata = ['06:00-07:00', '07:00-08:00', '08:00-09:00', '09:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
                '13:00-14:00', '14:00-15:00', '15:00-16:30', '15:00-17:30']

    #softwait(browser, '//*[@id="DualInfo_NewTimeSlotKey"]')
    wait_for_timeslots(browser, '//*[@id="DualInfo_NewTimeSlotKey"]')
    selectElem = Select(browser.find_element_by_xpath('//*[@id="DualInfo_NewTimeSlotKey"]'))

    print(f'Time Slot is {p.Timeslot}')
    if 'Hold' in p.Timeslot:
        return 'Error:  Did not select a timeslot for pin', True

    itime = p.Timeslot
    timeslotname = None

    sitems = selectElem.options
    sopts = len(sitems)
    timevec = []
    for i in sitems:
        timevec.append(i.text)
    print(f'We are looking for time slot {itime} in the vector of available times: {timevec}')

    for ix, td in enumerate(timevec):
        if itime in td:
            print(f'We have found timeslot {itime} in the the time available of: {td}')
            timeslotname = td
            iselect = ix

    if timeslotname is None:
            print('We have no matching timeslots, go to next available timeslot that IS available')
            for ix, td in enumerate(timedata):
                if itime in td:
                    for kx in range(ix+1, len(timedata)+1):
                        nexttimeslot = timedata[kx]
                        for jx, td in enumerate(timevec):
                            if nexttimeslot in td:
                                print(f'Need to adjust from timeslot {itime} to timeslot {nexttimeslot}')
                                timeslotname = td
                                iselect = jx
                                break
                        if timeslotname is not None: break
                if timeslotname is not None: break
    selectElem.select_by_index(iselect)

    # We now have the best available time slot selected

    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_LicensePlateNumber"]')
    selectElem.clear()
    selectElem.send_keys(p.Tag)

    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_DriverMobileNumber"]')
    selectElem.send_keys(d.Phone)

    ret_text = f'Pin made for {p.Driver} in Unit {p.Unit} time slot {timeslotname} chassis {p.InChas}'
    return ret_text, False

def wait_for_booking_result(browser, timeout=5):
    BOOKING_NOT_FOUND_XPATH = (
        "//div[@id='divBookingSummary']//td[normalize-space()='Booking was not found']"
    )

    PAST_BOOKING_XPATH = (
        "//div[@id='divBookingSummary']//td[normalize-space()='Past Booking']"
    )

    BOOKING_FULL_XPATH = (
        "//span[contains(@class,'error') and "
        "contains(normalize-space(),'All appointments have been made')]"
    )

    CHASSIS_XPATH = (
        "//*[@id='EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber']"
    )

    ALL_IS_WELL_XPATH = (
        "//*[@id='FullInAppts_0__ContainerNumber']"
    )

    wait = WebDriverWait(browser, timeout)

    wait.until(
        lambda d: (
                d.find_elements(By.XPATH, BOOKING_NOT_FOUND_XPATH)
                or d.find_elements(By.XPATH, BOOKING_FULL_XPATH)
                or d.find_elements(By.XPATH, PAST_BOOKING_XPATH)
                or d.find_elements(By.XPATH, CHASSIS_XPATH)
                or d.find_elements(By.XPATH, ALL_IS_WELL_XPATH)
        )
    )

    # ❌ Booking not found
    err = browser.find_elements(By.XPATH, BOOKING_NOT_FOUND_XPATH)
    if err:
        return err[0].text.strip(), True

    err = browser.find_elements(By.XPATH, PAST_BOOKING_XPATH)
    if err:
        return err[0].text.strip(), True

    # ❌ Booking full
    err = browser.find_elements(By.XPATH, BOOKING_FULL_XPATH)
    if err:
        return err[0].text.strip(), True

    # ✅ Success path, or if time out looking for an error
    return 'continue', False

def wait_for_container_result(browser, timeout=15):
    # This function checks to see if the container associated with a pin reservation is allowed to be pulled
    # from the port and if it is not it returns the error messages.  If no error it allow continuation
    # INLINE_ERROR_XPATH = (
    #    "//span[contains(@class,'error') and "
    #    "contains(text(),'Unable to create pre-advise')]"
    # )
    ERROR_SPANS_XPATH = "//*[contains(@class,'error')]"

    # The element that only appears if container is accepted
    PIN_XPATH = "//*[@id='ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber']"
    #'//*[@id="EmptyInAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]'
    wait = WebDriverWait(browser, timeout)

    elems = wait.until(
        lambda d: (
                d.find_elements(By.XPATH, ERROR_SPANS_XPATH)
                or d.find_elements(By.XPATH, PIN_XPATH)
        )
    )
    # Check for errors first
    error_spans = browser.find_elements(By.XPATH, ERROR_SPANS_XPATH)
    if error_spans:
        msg = " ".join(
            s.text.strip()
            for s in error_spans
            if s.text.strip()
        )
        return msg, True

    # Otherwise success
    return 'continue', False

def logonfox(err):
    username = usernames['gate']
    password = passwords['gate']
    print('username,password=', username, password)
    print('Entering Firefox') if printif == 1 else 1
    logontrys = 1
    logonyes = 0
    url1 = websites['gate']
    newurl = ''

    browser = webdriver.Firefox()
    #chatgpt says better to set window size explicitly in headless mode
    #browser.set_window_size(1920, 1080)
    browser.maximize_window()
    browser.get(url1)
    wait = WebDriverWait(browser, 30)

    print(f'Logon try {logontrys}')

    try:
        # Username
        user_elem = wait.until(
            EC.visibility_of_element_located((By.ID, "UserName"))
        )
        user_elem.clear()
        user_elem.send_keys(username)

        # Password
        pass_elem = wait.until(
            EC.visibility_of_element_located((By.ID, "Password"))
        )
        pass_elem.clear()
        pass_elem.send_keys(password)
        pass_elem.submit()

    except TimeoutException:
        err.append('Login fields did not appear within timeout')
        return browser, newurl, logonyes, logontrys, err

    # Wait for successful navigation (URL change)
    try:
        wait.until(lambda d: 'logon' not in d.current_url)
        logonyes = 1
        newurl = browser.current_url
    except TimeoutException:
        err.append('Login failed after submit')
        return browser, newurl, logonyes, logontrys, err

    if logonyes:
        newurl = newurl + '#/appointment/LimitedPreAdvise'

    return browser, newurl, logonyes, logontrys, err


def pinscraper(p,d,inbox,outbox,intype,outtype,browser,url,jx):
    pinget = 0
    thisdate = datetime.strftime(p.Date + timedelta(0), '%m/%d/%Y')
    elog = []
    print(f'The pins will be created for date: {thisdate} for url {url}')
    #list of xpaths and ids:
    #preadvise In checkbox
    in_checkbox_xp = '//*[@id="IsInMove"]'
    #New pre-advise drop down select active after in checkbox
    select_in_xp = '//*[@id="PrimaryMoveType"]'
    # If select in is empty in then form appears with date, timeslot, plate, phone, container, chassis
    # time does not populated until date populates
    date_xp = '//*[@id="DualInfo_NewApptDate"]'
    time_xp = '//*[@id="DualInfo_NewTimeSlotKey"]'
    plate_xp = '//*[@id="DualInfo_LicensePlateNumber"]'
    phone_xp = '//*[@id="DualInfo_DriverMobileNumber"]'
    empty_in_container_xp = '//*[@id="EmptyInAppts_0__ApptInfo_ContainerNumber"]'
    # after empty in container number is entered, need to wait for ship line to populate automatially
    empty_in_ssco_xp = '//*[@id="EmptyInAppts_0__ApptInfo_SscoCode"]'
    # after all above populated, then after chassis entered the whole form will submit
    empty_in_chassis_xp = '//*[@id="EmptyInAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]'

    # For a load in then we have there xpaths:
    full_in_booking_xp = '//*[@id="BookingNumber"]'
    full_in_container_xp = '// *[ @ id = "FullInAppts_0__ContainerNumber"]'
    full_in_chassis_xp = '//*[@id="FullInAppts_0__ExpressGateModel_MainMove_ChassisNumber"]'

    #For the outbound moves
    #preadvise Out checkbox
    out_checkbox_xp = '//*[@id="IsOutMove"]'
    #New pre-advise drop down select active after in checkbox
    select_out_xp = '//*[@id="SecondaryMoveType"]'
    #Empty Out Chassis
    empty_out_chassis_xp = '//*[@id="EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber"]'
    # Load Out
    load_out_bolpin_xp = '//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber"]'
    load_out_chassis_xp = '//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]'

    textboxx = "//*[contains(text(),'Pre-Advise created successfully')]"
    closebutx = "//*[contains(@type,'button')]"

    if 1 == 1:
        browser.get(url)

        # Wait for the main In-Panel to appear
        WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.XPATH, in_checkbox_xp))
        )

        # This just waits for visibility, no need if above is completed
        #softwait(browser, '//*[@id="IsInMove"]')
        print('url=', url, flush=True)

        print(f'inbox is {inbox}')

        if inbox:
            print(f'URL at beginning of inbox section is {url}')
            #set_checkbox(browser, '//*[@id="IsInMove"]', checked=True) #Wait for and check the inbox
            checkbox = browser.find_element(By.XPATH, in_checkbox_xp)
            # Needs a Hard click
            browser.execute_script("arguments[0].click();", checkbox)

            WebDriverWait(browser, 10).until(
                lambda d: d.find_element(By.ID, "PrimaryMoveType").is_enabled()
            )

            #need to wait for page load here before moving forward or the appt information will not be settled
            Waitpageloadcomplete(browser)


            if intype == 'Load In':
                p.Notes = f'3) Started on Load In'
                db.session.commit()

                # This tested out for Load In
                hard_select_option(browser, "PrimaryMoveType", "Full In")

                Waitpageloadcomplete(browser)

                softwait(browser, full_in_booking_xp)
                type_entry(browser, full_in_booking_xp, p.InBook, 'ENTER')
                #selectElem = browser.find_element_by_xpath('//*[@id="BookingNumber"]')
                #selectElem.send_keys(p.InBook)
                #selectElem.submit()

                # We could have an issue with the booking for the load in so need to error check here
                text, error = wait_for_booking_result(browser)
                print(f'The load in text is {text} and error is {error}')
                if error:
                    print('Writing the error for booking inbound box to the database')
                    pinget = 0
                    p.Notes = f'Error: {text[:190]}'
                    p.Active = 0
                    modtext = f'Error on: {p.Intext}'
                    p.Intext = modtext
                    db.session.commit()
                    return

                # Dont have to softwait anymore becauce the wait_for_booking error check does this now
                #softwait(browser, '//*[@id="FullInAppts_0__ContainerNumber"]')

                #Load In Driver info
                note_text, error = fillapptdata(browser, d, p, thisdate)

                #Load In Completion of container and chassis
                type_entry(browser, full_in_container_xp, p.InCon, 'TAB')
                #selectElem = browser.find_element_by_xpath(full_in_container_xp)
                #selectElem.send_keys(p.InCon)
                # For a load in there is no container look up after entry need to move on
                chas = p.InChas
                if not hasinput(chas): chas = f'{scac}007'
                type_entry(browser, full_in_chassis_xp, chas, 'ENTER')
                #selectElem = browser.find_element_by_xpath(full_in_chassis_xp)
                #selectElem.send_keys(chas)
                #selectElem.submit()

                #Load In wait for textbox and extract
                #print(f'Performing softwait for textboxx: {textboxx}')
                #softwait_long(browser, textboxx)
                #pintext = get_text(browser, textboxx)
                pintext, error = get_result_message(browser)

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    try:
                        pinin = pins[0]
                        print(f'The load in pin is {pinin}')
                        pinget = 1
                        p.InPin = str(pinin)
                        p.OutPin = '1'
                        intext = p.Intext
                        if hasinput(intext):
                            p.Intext = f'[*{pinin}*] {intext}'
                        else:
                            p.Intext = f'[*{pinin}*] Load In: *{p.InBook}  {p.InCon}*'
                        db.session.commit()
                    except:
                        print(f'Could not locate the PIN text for Load In {p.InCon}')
                else:
                    p.Intext = f'Error: {p.Intext}'
                    p.Notes = f'Error: {pintext}'
                    p.Active = 0
                    db.session.commit()
                    return

                closethepopup(browser, closebutx)

            #This is the empty in section
            else:

                # Empty In Start with Container number
                p.Notes = f'4) Started on Empty In'
                db.session.commit()

                hard_select_option(browser, "PrimaryMoveType", "Empty In")
                print(f'Hard Select Completed')
                p.Notes = f'Empty In Hard Select Completed'
                db.session.commit()

                Waitpageloadcomplete(browser)

                # Empty In Appointment Data, Appt Data will go from Date to Chassis, but function
                # Just fills in the date, time, tag, and phone number then returns for
                # Rest of form
                note_text, error = fillapptdata(browser, d, p, thisdate)

                softwait(browser, empty_in_container_xp)
                selectElem = browser.find_element_by_xpath(empty_in_container_xp)
                selectElem.send_keys(p.InCon)
                selectElem.send_keys(Keys.TAB)
                Waitpageloadcomplete(browser)

                # With container entered the form must validate the container info
                # and will then populate several form boxes
                # But if the container cannot be returned we will get an error message here

                # Once we move to next block the form will populate the SSCO for the container selected
                elem = WebDriverWait(browser, 20).until(
                    lambda d: (e := d.find_element(By.XPATH, empty_in_ssco_xp)) and
                              (e if e.get_attribute("value") else False)
                )
                value = elem.get_attribute("value")
                print("SSCO value:", value)

                #Empty In Completion for Chassis
                chas = p.InChas
                if not hasinput(chas): chas = f'{scac}007'
                type_entry(browser, empty_in_chassis_xp, chas, 'ENTER')
                #chasElem = browser.find_element_by_xpath(empty_in_chassis_xp)
                #chasElem.send_keys(chas)
                # Need to wait here for loading, otherwise the SSL that goes with the container may not populate
                #chasElem.submit()

                # Empty In wait for textbox and extract
                # softwait_long(browser, textboxx)
                pintext, error = get_result_message(browser)
                # pintext = get_text(browser, textboxx)

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    pinin = pins[0]
                    print(f'The empty in pin is {pinin}')
                    pinget = 1
                    p.InPin = str(pinin)
                    p.OutPin = '1'
                    intext = p.Intext
                    if hasinput(intext):
                        p.Intext = f'[*{pinin}*] {intext}'
                    else:
                        p.Intext = f'[*{pinin}*] Empty In: *{p.InCon}*'
                    db.session.commit()

                else:
                    p.Intext = f'Error: {p.Intext}'
                    p.Notes = f'Error: {pintext}'
                    p.Active = 0
                    db.session.commit()
                    return
                closethepopup(browser, closebutx)

        if outbox:
            # Had to make these changes for headless mode, it sometimes failed otherwise
            print(f'URL at beginning of outbox section is {url}')
            #set_checkbox(browser, '//*[@id="IsInMove"]', checked=True) #Wait for and check the inbox
            checkbox = browser.find_element(By.XPATH, out_checkbox_xp)
            # Needs a Hard click
            browser.execute_script("arguments[0].click();", checkbox)

            Waitpageloadcomplete(browser)

            #checkbox = WebDriverWait(browser, 10).until(
            #    EC.element_to_be_clickable((By.ID, "IsOutMove"))
            #)
            #browser.execute_script("arguments[0].click();", checkbox)

            WebDriverWait(browser, 10).until(
                lambda d: d.find_element(By.ID, "SecondaryMoveType").is_enabled()
            )
            #need to wait for page load here before moving forward or the appt information will not be settled
            Waitpageloadcomplete(browser)

            if outtype == 'Empty Out':
                p.Notes = f'5) Started on Empty Out'
                db.session.commit()

                # This tested out for Load In
                hard_select_option(browser, "SecondaryMoveType", "Empty Out")

                #Select(selectElem).select_by_value('ExportsEmptyOut')

                # We need to know if inbox because there is different about of things to do depending...
                if not inbox:

                    booking = WebDriverWait(browser, 20).until(
                        EC.element_to_be_clickable((By.ID, "BookingNumber"))
                    )
                    booking.clear()
                    booking.send_keys(p.OutBook)
                    booking.submit()

                    text, error = wait_for_booking_result(browser)
                    print(f'The empty out text with no inbox is {text} and error is {error}')
                    if error:
                        print('Writing the error for booking with no inbound box to the database')
                        pinget = 0
                        p.Notes = f'Error: {text[:190]}'
                        p.Active = 0
                        modtext = f'Error on: {p.Outtext}'
                        p.Outtext = modtext
                        db.session.commit()
                        return

                    #If there is no incoming box then we have to fill the driver data also
                    softwait(browser, empty_out_chassis_xp)
                    note_text, error = fillapptdata(browser, d, p, thisdate)
                    type_entry(browser, empty_out_chassis_xp, p.OutChas, 'ENTER')
                    #selectElem = browser.find_element_by_xpath(empty_out_chassis_xp)
                    #selectElem.send_keys(p.OutChas)
                    #selectElem.submit()
                else:
                    # If there is an inbox, then there is the possibility of two elements with ID=bookingnumber,
                    # and that greatly complicates selenium search to find correct element, we need to restrain
                    # it to the outbox section

                    # The information is different with inbox already setting the chassis and appt information, just have to find and hit the submit button
                    panel_xpath = "//div[@id='divUpdatePanel-OUT']"

                    out_panel = WebDriverWait(browser, 20).until(
                        EC.presence_of_element_located((By.XPATH, panel_xpath))
                    )

                    booking = WebDriverWait(browser, 20).until(
                        lambda d: (
                                      el := out_panel.find_elements(By.XPATH, ".//input[@id='BookingNumber']")
                                  ) and el[0]
                    )

                    booking.clear()
                    booking.send_keys(p.OutBook)
                    booking.submit()

                    #Need to check here also if the booking exists
                    text, error = wait_for_booking_result(browser)
                    print(f'The empty out text with inbox is {text} and error is {error}')
                    if error:
                        print('Writing the error for booking with an inbound box to the database')
                        pinget = 0
                        p.Notes = f'Error: {text[:190]}'
                        p.Active = 0
                        modtext = f'Error on: {p.Outtext}'
                        p.Outtext = modtext
                        db.session.commit()
                        return


                    submit_btn = WebDriverWait(browser, 20).until(
                        EC.element_to_be_clickable((
                            By.XPATH,
                            f"{panel_xpath}//button[.//span[normalize-space()='Submit']]"
                        ))
                    )

                    browser.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", submit_btn
                    )

                    ActionChains(browser) \
                        .move_to_element(submit_btn) \
                        .pause(0.1) \
                        .click() \
                        .perform()


                print(f'Locating element with text: {textboxx}')
                #softwait_long(browser, textboxx)
                pintext, error = get_result_message(browser)

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    pinout = pins[0]
                    print(f'The empty out pin is {pinout}')
                    pinget = 1
                    p.OutPin = str(pinout)
                    outtext = p.Outtext
                    if hasinput(outtext):
                        p.Outtext = f'[*{pinout}*] {outtext}'
                    else:
                        p.Outtext = f'[*{pinout}*] Empty Out: *{p.OutBook}*'
                    db.session.commit()
                else:
                    #There is an error within the popup we need to display
                    print('Writing the error for empty out with a good booking but no pintext found')
                    pinget = 0
                    p.Notes = f'Error: {pintext[:190]}'
                    p.Active = 0
                    modtext = f'Error on: {p.Outtext}'
                    p.Outtext = modtext
                    db.session.commit()

                closethepopup(browser, closebutx)

            if outtype == 'Load Out':
                p.Notes = f'6) Started on Load Out'
                db.session.commit()

                #Select(selectElem).select_by_value('ImportsFullOut')
                hard_select_option(browser, "SecondaryMoveType", "Import Out")

                # Scope the container number input to the OUT panel
                panel_xpath = "//div[@id='divUpdatePanel-OUT']"
                container_xpath = f"{panel_xpath}//input[@id='ContainerNumber']"

                containerid = WebDriverWait(browser, 20).until(
                    EC.element_to_be_clickable((By.XPATH, container_xpath))
                )

                containerid.clear()
                containerid.send_keys(p.OutCon)
                containerid.submit()

                #Check here for error on container pull, instant errors like unavailable
                text, error = wait_for_container_result(browser)
                print(f'The load out text is {text} and error is {error}')
                if error:
                    pinget = 0
                    p.Notes = f'Error: {text[:190]}'
                    p.Active = 0
                    modtext = f'Error on: {p.Outtext}'
                    p.Outtext = modtext
                    db.session.commit()
                    return


                #softwait(browser, '//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber"]')

                # Only fill in the driver/truck data if no in box, otherwise it is there already
                if not inbox:
                    note_text, error = fillapptdata(browser, d, p, thisdate)
                    if error:
                        pinget = 0
                        p.Notes = note_text
                        db.session.commit()
                        return

                    selectElem = browser.find_element_by_xpath(load_out_bolpin_xp)
                    selectElem.send_keys(p.OutBook)

                    selectElem = browser.find_element_by_xpath(load_out_chassis_xp)
                    chas = p.OutChas
                    if not hasinput(chas): chas = f'{scac}007'
                    type_entry(browser, load_out_chassis_xp, chas, 'ENTER')
                    #selectElem.send_keys(chas)
                    #selectElem.submit()

                else:
                    selectElem = browser.find_element_by_xpath(load_out_bolpin_xp)
                    type_entry(browser, load_out_bolpin_xp, p.OutBook, 'ENTER')
                    #selectElem.send_keys(p.OutBook)
                    #selectElem.submit()



                # The popup box is different if there is an incoming box....
                pintext, error = get_result_message(browser)
                print(f'The pintext found here is: {pintext} in element {selectElem}')

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    pinout = pins[0]
                    print(f'The load out pin is {pinout}')
                    pinget = 1
                    p.OutPin = str(pinout)
                    outtext = p.Outtext
                    outtext = outtext.replace("Error on: ", "")
                    if hasinput(outtext):
                        p.Outtext = f'[*{pinout}*] {outtext}'
                    else:
                        p.Outtext = f'[*{pinout}*] Load Out: *{p.OutBook}  {p.OutCon}*'
                    db.session.commit()
                else:
                    #There is an error within the popup we need to display
                    pinget = 0
                    p.Notes = f'Error: {pintext[:190]}'
                    p.Active = 0
                    outtext = p.Outtext
                    outtext = outtext.replace("Error on: ", "")
                    modtext = f'Error on: {outtext}'
                    p.Outtext = modtext
                    db.session.commit()

                closethepopup(browser, closebutx)

    if pinget:
        if inbox and not outbox:
            p.Outtext = 'Nothing Out'
            elog.append('Nothing Out')
        if outbox and not inbox:
            p.Intext = f'Bare chassis in {p.InChas}'
            elog.append(f'Bare chassis in {p.InChas}')
        p.Phone = d.Phone
        print(f'At end the note text is {note_text} and error is {error}')
        p.Notes = note_text
        db.session.commit()

    return elog

#*********************************************************************
conyes = 0
contrys = 0
nruns = 0



print(f'Attempting to connect to database and table Pins....')
while contrys < 4 and conyes == 0:
    try:
        #pdata = Pins.query.filter((Pins.OutPin == '0') & (Pins.Timeslot != 'Hold Getting') & (Pins.Date >= today)).all()
        pinid = int(pinid)
        print(f'Getting pin data for id {pinid}')
        pdat = Pins.query.filter(Pins.id == pinid).first()
        nruns = 1
        conyes = 1
    except:
        print(f'Could not connect to database on try {contrys}')
        contrys += 1
    time.sleep(1)

if nruns == 0 or conyes == 0:
    if conyes == 0:
        print('Could not connect to database')
    else:
        print(f'There are no pins required per database')
    quit()

if nruns > 0:
    maker = pdat.Maker
    active = pdat.Active
    timeslot = pdat.Timeslot
    pdat.Notes = f'1) Database opened and stating to get pin for id {pinid}'
    db.session.commit()

    if maker == 'WEB':
        print('This pin derived on WEB do not use this headless code to get')
    if active != 1:
        print('This pin not labeled as active')

    print(f'The pin database requires {nruns} new interchange sequences as follows:')

    if hasinput(pdat.InBook): intype = 'Load In'
    elif hasinput(pdat.InCon): intype = 'Empty In'
    else:
        intype = 'NoInType'
        inbox = 0

    if hasinput(pdat.OutCon): outtype = 'Load Out'
    elif hasinput(pdat.OutBook): outtype = 'Empty Out'
    else:
        outtype = 'NoOutType'
        outbox = 0
    print(f'Date: {pdat.Date} Driver: {pdat.Driver} Unit: {pdat.Unit} In-Type: {intype}  Out-Type: {outtype}')



if nruns > 0:
    logonyes = 0
    logontrys = 0
    #Log on to browser
    err = []
    elog = []

    with Display():
        browser, url, logonyes, logontrys, err = logonfox(err)
        if logonyes:
            print(f'Starting to get PIN {pdat.id}', flush=True)
            inbox = 1
            outbox = 1
            pdat.Notes = f'2) Database log on successful'
            db.session.commit()

            if hasinput(pdat.InBook): intype = 'Load In'
            elif hasinput(pdat.InCon): intype = 'Empty In'
            else:
                intype = 'NoInType'
                inbox = 0

            if hasinput(pdat.OutCon): outtype = 'Load Out'
            elif hasinput(pdat.OutBook): outtype = 'Empty Out'
            else:
                outtype = 'NoOutType'
                outbox = 0

            if outbox and inbox:
                if not hasinput(pdat.OutChas):
                    pdat.OutChas = pdat.InChas
                    db.session.commit()

            ddat = Drivers.query.filter(Drivers.Name==pdat.Driver).first()
            if ddat is not None:
                print(f'We have driver {ddat.Name} with phone {ddat.Phone}')
                print(f'We have driver {ddat.Name} driving truck {pdat.Unit} with tag {pdat.Tag}')
                print(f'On date {pdat.Date} we have intype {intype} in-booking {pdat.InBook} and in-container {pdat.InCon} and in-chassis {pdat.InChas}')
                print(f'On date {pdat.Date} we have outtype {outtype} Out-booking {pdat.OutBook} and Out-container {pdat.OutCon} and Out-chassis {pdat.OutChas}')

                print(f'Starting pinscraper for pin {pdat.id}', flush=True)
                if 1 == 1:
                    elog = pinscraper(pdat,ddat,inbox,outbox,intype,outtype,browser,url,0)
                if 1 == 2:
                    pdat.Notes = f'Failed to get pin {pdat.id}'
                    db.session.commit()
                print(f'Returning from pinscraper for pin {pdat.id}', flush=True)

            else:
                print(f'There is incomplete data for driver {pdat.Driver}')
                elog = (f'There is incomplete data for driver {pdat.Driver}')
                pdat.Notes = f'Failed because driver not found'
                db.session.commit()

    browser.quit()

if nt == 'remote': tunnel.stop()
