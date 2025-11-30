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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import *
from utils import hasinput
from selenium.webdriver.firefox.options import Options

import logging

logging.basicConfig(
    filename='/tmp/selenium_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


#Handle the input arguments from script file
#Handle the input arguments from script file
po = True

try:
    scac = sys.argv[1]
    nt = 'remote'
    if po: print(f'Received input argument of SCAC: {scac}')
except:
    if po: print('Must have a SCAC code argument or will get from setup file')
    if po: print('Setting SCAC to FELA since none provided')
    scac = 'fela'
    nt = 'remote'
    quit()


try:
    pinid = sys.argv[2]
    if po: print(f'Received input argument of pinid: {pinid}')
except:
    if po: print('Must have a second argument for which pin to run')
    quit()

# THIRD ARGUMENT: behavior mode
try:
    mode = sys.argv[3].lower()
    if po: print(f'Received mode argument: {mode}')
except:
    mode = 'run'   # default
    if po: print('No mode argument. Defaulting to RUN.')


scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    if po: print(f'Running FFF_make_pins for {scac} in tunnel mode: {nt}')

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
if po: print(' ')
if po: print('_______________________________________________________')
if po: print(f'This sequence run date: {today}')
if po: print('_______________________________________________________')
if po: print(' ')
textblock = f'This sequence run at {runat} and minutes are {mins}\n'

def get_all_needpin():
    return Pins.query.filter(Pins.message == 'NeedPin').all()


def closethepopup(browser, closebutx):
    handles = browser.window_handles
    for handle in handles:
        if po: print(f'In closethepop we have handle: {handle}')
    if po: print(f'We are using handle {browser.current_window_handle}')
    closebuts = browser.find_elements_by_xpath(closebutx)
    if closebuts:
        for closebut in closebuts:
            if po: print(f'closebut: {closebut.text}')
            if closebut.text == 'Close': closebut.click()
def softwait(browser, xpath):
    closebutx = "//*[contains(@type,'button')]"
    try:
        wait = WebDriverWait(browser, 16, poll_frequency=2,ignored_exceptions=[ElementNotVisibleException, ElementNotSelectableException])
        elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        time.sleep(1)
        #elem = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, xpath)))
    except:
        textboxes = browser.find_elements_by_xpath(xpath)
        if textboxes:
            for textbox in textboxes:
                if po: print(f'Finding textboxes on page: {textbox.text}')
    return

def softwait_long(browser, xpath):
    closebutx = "//*[contains(@type,'button')]"
    try:
        wait = WebDriverWait(browser, 30, poll_frequency=2,ignored_exceptions=[ElementNotVisibleException, ElementNotSelectableException])
        elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        time.sleep(1)
        #elem = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, xpath)))
    except:
        textboxes = browser.find_elements_by_xpath(xpath)
        if textboxes:
            for textbox in textboxes:
                if po: print(f'Finding textboxes on page: {textbox.text}')
    return

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

def fillapptdata(browser, d, p, thisdate):
    softwait(browser, '//*[@id="DualInfo_NewApptDate"]')
    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_NewApptDate"]')
    selectElem.send_keys(thisdate)
    selectElem.submit()
    time.sleep(3)

    timedata = ['06:00-07:00', '07:00-08:00', '08:00-09:00', '09:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
                '13:00-14:00', '14:00-15:00', '15:00-16:30', '15:00-17:30']

    softwait(browser, '//*[@id="DualInfo_NewTimeSlotKey"]')
    selectElem = Select(browser.find_element_by_xpath('//*[@id="DualInfo_NewTimeSlotKey"]'))
    time.sleep(1)
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
    #selectElem.send_keys('7578973266')

    #selectElem = Select(browser.find_element_by_xpath('// *[ @ id = "mobileCarrier"]'))
    #time.sleep(1)
    #selectElem.select_by_visible_text(d.Carrier)
    ret_text = f'Pin made for {p.Driver} in Unit {p.Unit} time slot {timeslotname} chassis {p.InChas}'
    return ret_text

def logonfox(err):
    # First time thru need to logon
    printif = 1
    username = usernames['gate']
    password = passwords['gate']
    if po: print('username,password=', username, password)
    if po: print('Entering Firefox') if printif == 1 else 1
    logontrys = 1
    logonyes = 0
    url1 = websites['gate']
    newurl = ''
    #with Display():
    #display = Display(visible=0, size=(800, 1080))
    #display.start()
    if 1 == 1:
        #browser = webdriver.Firefox()
        #browser.maximize_window()
        browser = webdriver.Firefox(options=options)

        browser.get(url1)
        if po: print(f'Logon try {logontrys} for url: {url1}')
        if 1 == 1:
            softwait(browser, '//*[@id="UserName"]')
            selectElem = browser.find_element_by_xpath('//*[@id="UserName"]')
            if po: print('Got xpath for Username') if printif == 1 else 1
            selectElem.clear()
            selectElem.send_keys(username)
        if 1 == 2:
            err.append('Username did not appear within 30 sec try again')
            return browser, newurl, logonyes, logontrys, err


        try:
            selectElem = browser.find_element_by_xpath('//*[@id="Password"]')
            if po: print('Got xpath for Password') if printif == 1 else 1
            selectElem.clear()
            selectElem.send_keys(password)
            time.sleep(1)
            selectElem.submit()
            time.sleep(8)
            if po: print('Page should be loaded now')
        except:
            err.append('Page did not load within 5 sec try again')
            if po: print('Page did not load within 5 sec try again')
            return browser, newurl, logonyes, logontrys, err


        while logontrys < 4 and logonyes == 0:
            newurl = browser.current_url
            time.sleep(1)
            if po: print('newurl=', newurl, flush=True)
            if 'logon' not in newurl:
                logonyes = 1
            else:
                if po: print(f'Log on failed on try {logontrys}')
            logontrys += 1

        if logonyes:
            newurl = newurl+'#/appointment/LimitedPreAdvise'

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
        softwait(browser, '//*[@id="IsInMove"]')
        #time.sleep(6)
        if po: print('url=', url, flush=True)
        textboxx = "//*[contains(text(),'Pre-Advise created successfully')]"
        waitboxx = "//*[contains(text(),'Pre-Advise created successfully')]"
        xp1 = "/html/body/div[14]/div[2]/table/tbody/tr[2]/td[4]"
        xp2 = "/html/body/div[16]/div[2]/table/tbody/tr[2]/td[3]"
        xp3 = "/html/body/div[16]/div[2]/table/tbody/tr[2]/td[4]"
        #textboxx = "//*[contains(text(),'Pre-Advise created successfully')]"
        #waitboxx = "apptStatus"
        #textboxx = f'{xp1} | {xp2} | {xp3}'
        #waitboxx = f'{xp1} | {xp2} | {xp3}'
        closebutx = "//*[contains(@type,'button')]"

        if po: print(f'inbox is {inbox}')
        if inbox:
            selectElem = browser.find_element_by_xpath('//*[@id="IsInMove"]')
            selectElem.click()
            selectElem = Select(browser.find_element_by_xpath('//*[@id="PrimaryMoveType"]'))

            if intype == 'Load In':

                #Load In Starts with Booking
                selectElem.select_by_value('ExportsFullIn')
                time.sleep(1)
                softwait(browser, '//*[@id="BookingNumber"]')
                selectElem = browser.find_element_by_xpath('//*[@id="BookingNumber"]')
                selectElem.send_keys(p.InBook)
                time.sleep(1)
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
                time.sleep(1)
                selectElem.submit()

                #Load In wait for textbox and extract
                if po: print(f'Performing softwait for textboxx: {textboxx}')
                softwait_long(browser, textboxx)
                #softwait_popup(browser)
                #selectElem = browser.find_element_by_xpath(textboxx)
                #pintext = selectElem.text
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

                #Empty In Start with Container number
                selectElem.select_by_value('EmptyIn')
                time.sleep(1)

                #selectElem = browser.find_element_by_xpath('//*[@id="ContainerNumber"]')
                softwait(browser, '//*[@id="EmptyInAppts_0__ApptInfo_ContainerNumber"]')
                selectElem = browser.find_element_by_xpath('//*[@id="EmptyInAppts_0__ApptInfo_ContainerNumber"]')
                selectElem.send_keys(p.InCon)
                time.sleep(1)

                # Empty In Driver Data
                note_text = fillapptdata(browser, d, p, thisdate)

                #softwait(browser, "/html/body/div[1]/div[6]/div[5]/div[1]/div/div[3]/div[1]/form/div[2]/div/div[2]/button/span")

                #Empty In Completion for Chassis
                selectElem = browser.find_element_by_xpath('//*[@id="EmptyInAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]')
                chas = p.InChas
                if not hasinput(chas): chas = f'{scac}007'
                selectElem.send_keys(chas)
                time.sleep(1)
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
            #Selection for the out part...
            softwait(browser, '//*[@id="IsOutMove"]')
            time.sleep(1)
            selectElem = browser.find_element_by_xpath('//*[@id="IsOutMove"]')
            time.sleep(1)
            selectElem.click()
            time.sleep(1)

            if outtype == 'Empty Out':
                #Empty Out Start with Booking
                softwait(browser, '//*[@id="SecondaryMoveType"]')
                selectElem = Select(browser.find_element_by_xpath('//*[@id="SecondaryMoveType"]'))
                selectElem.select_by_value('ExportsEmptyOut')
                if not inbox:
                    softwait(browser, '//*[@id="BookingNumber"]')
                    selectElem = browser.find_element_by_xpath('//*[@id="BookingNumber"]')
                else:
                    softwait(browser, '/html/body/div[1]/div[6]/div[5]/div[2]/div[1]/form/div/div[2]/div[1]/input')
                    selectElem = browser.find_element_by_xpath('/html/body/div[1]/div[6]/div[5]/div[2]/div[1]/form/div/div[2]/div[1]/input')
                selectElem.send_keys(p.OutBook)
                time.sleep(1)
                selectElem.submit()

                if not inbox:
                    #If there is no incoming box then we have to fill the driver data also
                    softwait(browser, '//*[@id="EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                    note_text = fillapptdata(browser, d, p, thisdate)
                    selectElem = browser.find_element_by_xpath('//*[@id="EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                    selectElem.send_keys(p.OutChas)
                    time.sleep(1)
                    selectElem.submit()
                else:
                    #If coming off an incoming box then just need to continue
                    softwait(browser, '/html/body/div[1]/div[6]/div[5]/div[2]/div[1]/div[3]/form/div[5]/div/button/span')
                    selectElem = browser.find_element_by_xpath('/html/body/div[1]/div[6]/div[5]/div[2]/div[1]/div[3]/form/div[5]/div/button/span')
                    selectElem.click()
                    if po: print('Made it past this point')


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
                selectElem = Select(browser.find_element_by_xpath('//*[@id="SecondaryMoveType"]'))
                time.sleep(1)
                selectElem.select_by_value('ImportsFullOut')
                time.sleep(1)

                # if empty in there will be two container number xpaths, have to use full xpath....
                if intype == 'Empty In':
                    softwait(browser, '/html/body/div[1]/div[6]/div[5]/div[2]/div/form/div/div[1]/div/input')
                    selectElem = browser.find_element_by_xpath('/html/body/div[1]/div[6]/div[5]/div[2]/div/form/div/div[1]/div/input')
                else:
                    softwait(browser, '//*[@id="ContainerNumber"]')
                    selectElem = browser.find_element_by_xpath('//*[@id="ContainerNumber"]')

                selectElem.send_keys(p.OutCon)
                time.sleep(1)
                selectElem.submit()

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
                time.sleep(1)
                selectElem.submit()

                # The popup box is different of there is an incoming box....
                softwait_long(browser, textboxx)
                #selectElem = browser.find_element_by_xpath(textboxx)
                #pintext = selectElem.text
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

if mode == 'status':
    status = {
        "running": True,
        "scac": scac,
        "current_pin": pinid,
        "timestamp": datetime.now().isoformat()
    }
    print(status)
    sys.exit(0)

if mode == 'all'
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
        if maker == 'WEB':
            if po: print('This pin derived on WEB do not use this headless code to get')
        if active != 1:
            if po: print('This pin not labeled as active')

        if po: print(f'The pin database requires {nruns} new interchange sequences as follows:')
        if 1 == 1:
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
                print(f'PROGRESS: Starting PIN {pdat.id}', flush=True)

                jx = 0
                if 1 == 1:
                #for jx, pdat in enumerate(pdata):
                    inbox = 1
                    outbox = 1

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

                        print(f'PROGRESS: Starting PIN {pdat.id}', flush=True)
                        elog = pinscraper(pdat,ddat,inbox,outbox,intype,outtype,browser,url,jx)
                        print(f'PROGRESS: Finished PIN {pdat.id}', flush=True)

                    else:
                        if po: print(f'There is incomplete data for driver {pdat.Driver}')
                        elog = (f'There is incomplete data for driver {pdat.Driver}')

                browser.quit()
                for elo in elog:
                    print(elo)


            else:
                browser.quit()

if nt == 'remote': tunnel.stop()
