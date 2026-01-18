import os
import sys

import socket
from utils import getpaths

from bs4 import BeautifulSoup as soup
import time
from datetime import datetime, timedelta
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import *
from selenium.webdriver.common.action_chains import ActionChains
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
    if po: print(f'Running FFF_make_pins_headless for {scac} for pinid {pinid} in tunnel mode: {nt}')
    host_name = socket.gethostname()
    if po: print("Host Name:", host_name)
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
    if po: print('The argument must be FELA or OSLM or NEVO')
    quit()

printif = 0
runat = datetime.now()
tnow = runat.strftime("%M")
mins = int(tnow)
today = runat.date()
textblock = f'This sequence run at {runat} and minutes are {mins}\n'

def safe_click(browser, elem):
    browser.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        elem
    )
    browser.execute_script("arguments[0].click();", elem)



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


def oldsoftwait(browser, xpath, timeout=16):
    try:
        wait = WebDriverWait(browser, timeout, poll_frequency=0.5)
        return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
    except TimeoutException:
        if po:
            print(f"Timed out waiting for element: {xpath}")
        return None

def softwait(browser, xpath, timeout=16):
    try:
        wait = WebDriverWait(browser, timeout, poll_frequency=0.5)
        return wait.until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )
    except TimeoutException:
        if po:
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

def safe_select_option(browser, panel_id, select_id, option_text, timeout=20):
    """
    Safely selects an option in a SPA select element.
    - panel_id: id of the container panel (IN or OUT)
    - select_id: id of the select element
    - option_text: visible text to select
    """
    panel_xpath = f"//div[@id='{panel_id}']"
    select_xpath = f"{panel_xpath}//select[@id='{select_id}']"

    for attempt in range(3):
        try:
            # Locate the current live element
            selectElem = WebDriverWait(browser, timeout).until(
                EC.element_to_be_clickable((By.XPATH, select_xpath))
            )

            # Scroll into view (important in headless)
            browser.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", selectElem
            )

            # Single ActionChains to click + send_keys
            ActionChains(browser).move_to_element(selectElem).click().send_keys(option_text).perform()

            return selectElem
        except StaleElementReferenceException:
            # Small wait and retry if SPA re-rendered the element
            time.sleep(0.2)

    raise Exception(f"Failed to select '{option_text}' on {select_id}")


from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import time


def hard_select_option(browser, select_id, option_text, timeout=20, retries=3):
    """
    Performs a 'hard' selection on a select box:
    - clicks into the select
    - sends keys for the option
    - triggers SPA JS
    Retries if element is stale.
    """
    for attempt in range(retries):
        try:
            # Wait until the select element is clickable
            selectElem = WebDriverWait(browser, timeout).until(
                EC.element_to_be_clickable((By.ID, select_id))
            )

            # Scroll into view (headless mode may need this)
            browser.execute_script("arguments[0].scrollIntoView({block:'center'});", selectElem)

            # Perform hard selection
            action = ActionChains(browser)
            action.move_to_element(selectElem).click().perform()
            time.sleep(0.1)  # tiny pause to ensure focus
            action.send_keys(option_text).perform()

            return selectElem

        except StaleElementReferenceException:
            # Element was replaced by JS, retry
            time.sleep(0.2)
        except TimeoutException:
            time.sleep(0.2)

    raise Exception(f"Failed to hard-select '{option_text}' in select '{select_id}'")


def get_text(browser, xpath):
    time.sleep(1)
    textboxes = browser.find_elements_by_xpath(xpath)
    time.sleep(1)
    if po: print(f'The textboxes for xpath {xpath} is {textboxes}')
    ret_text = 'xxxxx'
    if textboxes:
        for textbox in textboxes:
            thistext = textbox.text
            if po: print(f'Finding textboxes on page: {thistext}')
            if 'Pre-Advise PIN' in thistext: ret_text = thistext
    else:
        ret_text = 'No textboxes found'
    return ret_text

# Wait until the select has more than 1 option (skip placeholder 'Loading...')
def wait_for_timeslots(browser, xpath, timeout=20):

    def options_populated(driver):
        sel = driver.find_element(By.XPATH, xpath)
        return len(sel.find_elements(By.TAG_NAME, "option")) > 1  # >1 to skip placeholder

    return WebDriverWait(browser, timeout).until(options_populated)


def fillapptdata(browser, d, p, thisdate):
    softwait(browser, '//*[@id="DualInfo_NewApptDate"]')
    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_NewApptDate"]')
    selectElem.send_keys(thisdate)
    selectElem.submit()
    #time.sleep(3)

    timedata = ['06:00-07:00', '07:00-08:00', '08:00-09:00', '09:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
                '13:00-14:00', '14:00-15:00', '15:00-16:30', '15:00-17:30']

    #softwait(browser, '//*[@id="DualInfo_NewTimeSlotKey"]')
    wait_for_timeslots(browser, '//*[@id="DualInfo_NewTimeSlotKey"]')
    selectElem = Select(browser.find_element_by_xpath('//*[@id="DualInfo_NewTimeSlotKey"]'))
    #time.sleep(1)
    itime = p.Timeslot
    timeslotname = None

    sitems = selectElem.options
    sopts = len(sitems)
    timevec = []
    for i in sitems:
        timevec.append(i.text)
    if po: print(f'We are looking for time slot {itime} in the vector of available times: {timevec}')

    for ix, td in enumerate(timevec):
        if itime in td:
            if po: print(f'We have found timeslot {itime} in the the time available of: {td}')
            timeslotname = td
            iselect = ix

    if timeslotname is None:
            if po: print('We have no matching timeslots, go to next available timeslot that IS available')
            for ix, td in enumerate(timedata):
                if itime in td:
                    for kx in range(ix+1, len(timedata)+1):
                        nexttimeslot = timedata[kx]
                        for jx, td in enumerate(timevec):
                            if nexttimeslot in td:
                                if po: print(f'Need to adjust from timeslot {itime} to timeslot {nexttimeslot}')
                                timeslotname = td
                                iselect = jx
                                break
                        if timeslotname is not None: break
                if timeslotname is not None: break


    selectElem.select_by_index(iselect)

    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_LicensePlateNumber"]')
    selectElem.send_keys(p.Tag)
    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_DriverMobileNumber"]')
    selectElem.send_keys(d.Phone)
    ret_text = f'Pin made for {p.Driver} in Unit {p.Unit} time slot {timeslotname} chassis {p.InChas}'
    return ret_text

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
    if po: print(f'The pins will be created for date: {thisdate} for url {url}')

    #with Display():
        #display = Display(visible=0, size=(800, 1080))
        #display.start()
    if 1 == 1:
        browser.get(url)

        # Wait for the main appointment container to appear
        WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.XPATH, '//div[@id="divUpdatePanel-IN"]'))
        )

        softwait(browser, '//*[@id="IsInMove"]')
        #time.sleep(6)
        if po: print('url=', url, flush=True)
        textboxx = "//*[contains(text(),'Pre-Advise created successfully')]"
        closebutx = "//*[contains(@type,'button')]"
        if po: print(f'inbox is {inbox}')

        if inbox:
            print(f'URL at beginning of inbox section is {url}')
            #set_checkbox(browser, '//*[@id="IsInMove"]', checked=True) #Wait for and check the inbox
            checkbox = browser.find_element(By.XPATH, '//*[@id="IsInMove"]')
            # Needs a Hard click
            browser.execute_script("arguments[0].click();", checkbox)

            # Wait for SPA re-render to complete
            #WebDriverWait(browser, 20).until(
            #    EC.presence_of_element_located((By.XPATH, '//*[@id="PrimaryMoveType"]'))
            #)

            # Re-locate the element AFTER render
            #selectElem = browser.find_element(By.XPATH, '//*[@id="PrimaryMoveType"]')
            #selectElem = browser.find_element(By.ID, "PrimaryMoveType")

            if intype == 'Load In':
                p.Notes = f'3) Started on Load In'
                db.session.commit()

                #selectElem = browser.find_element(By.ID, "PrimaryMoveType")
                #selectElem = WebDriverWait(browser, 20).until(
                #EC.presence_of_element_located((By.XPATH, '//*[@id="PrimaryMoveType"]'))
                #)
                #selectElem = safe_select_option(browser, "divUpdatePanel-IN", "PrimaryMoveType", "Full In")
                #action = ActionChains(browser)
                #action.move_to_element(selectElem).click().perform()
                # Send keys to select option
                #action.send_keys("Full In").perform()

                selectElem = hard_select_option(browser, "PrimaryMoveType", "Full In")


                #Load In Starts with Booking
                #Select(selectElem).select_by_value('ExportsFullIn')
                softwait(browser, '//*[@id="BookingNumber"]')
                selectElem = browser.find_element_by_xpath('//*[@id="BookingNumber"]')
                selectElem.send_keys(p.InBook)
                selectElem.submit()
                softwait(browser, '//*[@id="FullInAppts_0__ContainerNumber"]')

                #Load In Driver info
                note_text = fillapptdata(browser, d, p, thisdate)

                #Load In Completion of container and chassis
                selectElem = browser.find_element_by_xpath('//*[@id="FullInAppts_0__ContainerNumber"]')
                selectElem.send_keys(p.InCon)
                selectElem = browser.find_element_by_xpath('//*[@id="FullInAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                chas = p.InChas
                if not hasinput(chas): chas = f'{scac}007'
                selectElem.send_keys(chas)
                selectElem.submit()

                #Load In wait for textbox and extract
                if po: print(f'Performing softwait for textboxx: {textboxx}')
                softwait_long(browser, textboxx)
                pintext = get_text(browser, textboxx)
                pins = [int(s) for s in pintext.split() if s.isdigit()]
                try:
                    pinin = pins[0]
                    if po: print(f'The load in pin is {pinin}')
                    pinget = 1
                    p.InPin = str(pinin)
                    p.OutPin = '1'
                    intext = p.Intext
                    if hasinput(intext):
                        p.Intext = f'[*{pinin}*] {intext}'
                        elog.append(f'[*{pinin}*] {intext}')
                    else:
                        p.Intext = f'[*{pinin}*] Load In: *{p.InBook}  {p.InCon}*'
                        elog.append(f'[*{pinin}*] Load In: *{p.InBook}  {p.InCon}*')
                    db.session.commit()
                except:
                    if po: print(f'Could not locate the PIN text for Load In {p.InCon}')
                    elog.append(f'Could not locate the PIN text for Load In {p.InCon}')
                closethepopup(browser, closebutx)

            else:
                p.Notes = f'4) Started on Empty In'
                db.session.commit()

                selectElem = browser.find_element(By.ID, "PrimaryMoveType")
                action = ActionChains(browser)
                action.move_to_element(selectElem).click().perform()
                # Send keys to select option
                action.send_keys("Empty In").perform()

                #selectElem = browser.find_element_by_xpath('//*[@id="ContainerNumber"]')
                softwait(browser, '//*[@id="EmptyInAppts_0__ApptInfo_ContainerNumber"]')
                selectElem = browser.find_element_by_xpath('//*[@id="EmptyInAppts_0__ApptInfo_ContainerNumber"]')
                selectElem.send_keys(p.InCon)
                #time.sleep(1)

                # Empty In Driver Data
                note_text = fillapptdata(browser, d, p, thisdate)

                #softwait(browser, "/html/body/div[1]/div[6]/div[5]/div[1]/div/div[3]/div[1]/form/div[2]/div/div[2]/button/span")

                #Empty In Completion for Chassis
                selectElem = browser.find_element_by_xpath('//*[@id="EmptyInAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]')
                chas = p.InChas
                if not hasinput(chas): chas = f'{scac}007'
                selectElem.send_keys(chas)
                #time.sleep(1)
                selectElem.submit()

                #Empty In wait for textbox and extract
                softwait_long(browser, textboxx)
                #selectElem = browser.find_element_by_xpath(textboxx)
                #pintext = selectElem.text
                pintext = get_text(browser, textboxx)
                pins = [int(s) for s in pintext.split() if s.isdigit()]
                pinin = pins[0]
                if po: print(f'The empty in pin is {pinin}')
                pinget = 1
                p.InPin = str(pinin)
                p.OutPin = '1'
                intext = p.Intext
                if hasinput(intext):
                    p.Intext = f'[*{pinin}*] {intext}'
                    elog.append(f'[*{pinin}*] {intext}')
                else:
                    p.Intext = f'[*{pinin}*] Empty In: *{p.InCon}*'
                    elog.append(f'[*{pinin}*] Empty In: *{p.InCon}*')
                db.session.commit()
                closethepopup(browser, closebutx)

        if outbox:
            print(f'URL at beginning of outbox section is {url}')
            checkbox = browser.find_element(By.XPATH, '//*[@id="IsOutMove"]')
            # Needs a Hard click
            browser.execute_script("arguments[0].click();", checkbox)
            # Wait for dropdown to be enabled
            selectElem = WebDriverWait(browser, 16).until(
                lambda d: d.find_element(By.XPATH, '//*[@id="SecondaryMoveType"]') if
                d.find_element(By.XPATH, '//*[@id="SecondaryMoveType"]').is_enabled() else False
            )

            if outtype == 'Empty Out':
                p.Notes = f'5) Started on Empty Out'
                db.session.commit()
                Select(selectElem).select_by_value('ExportsEmptyOut')
                booking = WebDriverWait(browser, 20).until(
                    EC.element_to_be_clickable((By.ID, "BookingNumber"))
                )
                booking.clear()
                booking.send_keys(p.OutBook)
                booking.submit()

                # We need to know if inbox because there is different about of things to do depending...
                if not inbox:
                    #If there is no incoming box then we have to fill the driver data also
                    softwait(browser, '//*[@id="EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                    note_text = fillapptdata(browser, d, p, thisdate)
                    selectElem = browser.find_element_by_xpath('//*[@id="EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                    selectElem.send_keys(p.OutChas)
                    selectElem.submit()
                else:
                    #The information is different with inbox already setting the chassis and appt information, just have to find and hit the submit button
                    panel_xpath = "//div[@id='divUpdatePanel-OUT']"

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

                    print('Made it past this point where we use full xpath because have the inbox also')


                if po: print(f'Locating element with text: {textboxx}')
                softwait_long(browser, textboxx)
                #selectElem = browser.find_element_by_xpath(textboxx)
                #pintext = selectElem.text
                pintext = get_text(browser, textboxx)
                pins = [int(s) for s in pintext.split() if s.isdigit()]
                pinout = pins[0]
                if po: print(f'The empty out pin is {pinout}')
                pinget = 1
                p.OutPin = str(pinout)
                outtext = p.Outtext
                if hasinput(outtext):
                    p.Outtext = f'[*{pinout}*] {outtext}'
                    elog.append(f'[*{pinout}*] {outtext}')
                else:
                    p.Outtext = f'[*{pinout}*] Empty Out: *{p.OutBook}*'
                    elog.append(f'[*{pinout}*] Empty Out: *{p.OutBook}*')
                db.session.commit()
                closethepopup(browser, closebutx)

            if outtype == 'Load Out':
                p.Notes = f'6) Started on Load Out'
                db.session.commit()
                Select(selectElem).select_by_value('ImportsFullOut')

                # Scope the container number input to the OUT panel
                panel_xpath = "//div[@id='divUpdatePanel-OUT']"
                container_xpath = f"{panel_xpath}//input[@id='ContainerNumber']"

                containerid = WebDriverWait(browser, 20).until(
                    EC.element_to_be_clickable((By.XPATH, container_xpath))
                )

                containerid.clear()
                containerid.send_keys(p.OutCon)
                containerid.submit()

                softwait(browser, '//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber"]')

                # Only fill in the driver/truck data if no in box, otherwise it is there already
                if not inbox: note_text = fillapptdata(browser, d, p, thisdate)

                selectElem = browser.find_element_by_xpath('//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber"]')
                selectElem.send_keys(p.OutBook)

                # Only input the chassis number for the outbox if there is no inbox
                if not inbox:
                    selectElem = browser.find_element_by_xpath('//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]')
                    chas = p.OutChas
                    if not hasinput(chas): chas = f'{scac}007'
                    selectElem.send_keys(chas)

                selectElem.submit()

                # Only input the chassis number for the outbox if there is no inbox
                if not inbox:
                    selectElem = browser.find_element_by_xpath('//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]')
                    chas = p.OutChas
                    if not hasinput(chas): chas = f'{scac}007'
                    selectElem.send_keys(chas)
                selectElem.submit()

                # The popup box is different of there is an incoming box....
                softwait_long(browser, textboxx)
                pintext = get_text(browser, textboxx)
                if po: print(f'The pintext found here is: {pintext} in element {selectElem}')
                pins = [int(s) for s in pintext.split() if s.isdigit()]
                pinout = pins[0]
                if po: print(f'The load out pin is {pinout}')
                pinget = 1
                p.OutPin = str(pinout)
                outtext = p.Outtext
                if hasinput(outtext):
                    p.Outtext = f'[*{pinout}*] {outtext}'
                    elog.append(f'[*{pinout}*] {outtext}')
                else:
                    p.Outtext = f'[*{pinout}*] Load Out: *{p.OutBook}  {p.OutCon}*'
                    elog.append(f'[*{pinout}*] Load Out: *{p.OutBook}  {p.OutCon}*')
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
        p.Notes = note_text
        db.session.commit()

    return elog

#*********************************************************************
conyes = 0
contrys = 0
nruns = 0



if po: print(f'Attempting to connect to database and table Pins....')
while contrys < 4 and conyes == 0:
    try:
        #pdata = Pins.query.filter((Pins.OutPin == '0') & (Pins.Timeslot != 'Hold Getting') & (Pins.Date >= today)).all()
        pinid = int(pinid)
        if po: print(f'Getting pin data for id {pinid}')
        pdat = Pins.query.filter(Pins.id == pinid).first()
        nruns = 1
        conyes = 1
    except:
        if po: print(f'Could not connect to database on try {contrys}')
        contrys += 1
    time.sleep(1)

if nruns == 0 or conyes == 0:
    if conyes == 0:
        if po: print('Could not connect to database')
    else:
        if po: print(f'There are no pins required per database')
    quit()

if nruns > 0:
    maker = pdat.Maker
    active = pdat.Active
    timeslot = pdat.Timeslot
    pdat.Notes = f'1) Database opened and stating to get pin for id {pinid}'
    db.session.commit()

    if maker == 'WEB':
        if po: print('This pin derived on WEB do not use this headless code to get')
    if active != 1:
        if po: print('This pin not labeled as active')

    if po: print(f'The pin database requires {nruns} new interchange sequences as follows:')

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
    if po: print(f'Date: {pdat.Date} Driver: {pdat.Driver} Unit: {pdat.Unit} In-Type: {intype}  Out-Type: {outtype}')



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
                if po: print(f'We have driver {ddat.Name} with phone {ddat.Phone}')
                if po: print(f'We have driver {ddat.Name} driving truck {pdat.Unit} with tag {pdat.Tag}')
                if po: print(f'On date {pdat.Date} we have intype {intype} in-booking {pdat.InBook} and in-container {pdat.InCon} and in-chassis {pdat.InChas}')
                if po: print(f'On date {pdat.Date} we have outtype {outtype} Out-booking {pdat.OutBook} and Out-container {pdat.OutCon} and Out-chassis {pdat.OutChas}')

                print(f'Starting pinscraper for pin {pdat.id}', flush=True)
                if 1 == 1:
                    elog = pinscraper(pdat,ddat,inbox,outbox,intype,outtype,browser,url,0)
                if 1 == 2:
                    pdat.Notes = f'Failed to get pin {pdat.id}'
                    db.session.commit()
                print(f'Returning from pinscraper for pin {pdat.id}', flush=True)

            else:
                if po: print(f'There is incomplete data for driver {pdat.Driver}')
                elog = (f'There is incomplete data for driver {pdat.Driver}')
                pdat.Notes = f'Failed because driver not found'
                db.session.commit()

            for elo in elog:
                print(elo)

    browser.quit()

if nt == 'remote': tunnel.stop()
