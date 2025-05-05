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

import pdfkit
from PyPDF2 import PdfReader, PdfWriter, Transformation
#from PyPDF2 import PageObject
from utils import hasinput

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    nt = 'remote'
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    print('Setting SCAC to FELA since none provided')
    scac = 'oslm'
    nt = 'remote'

scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':

    print(f'Running FFF_task_gate_now for {scac} in tunnel mode: {nt}')
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
    from CCC_system_setup import websites, usernames, passwords, addpath3, addpath, addpaths
    from email_reports import emailtxt
    from cronfuncs import conmatch
else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO so getting inputs for CCC-system_setup')
    from CCC_system_setup import addpath3, websites, usernames, passwords, lt, scac, nt, addpath, addpaths
    from models8 import Interchange, Orders, Pins

printif = 0

runat = datetime.now()
tnow = runat.strftime("%M")
mins = int(tnow)
print(' ')
print('_____________________________________________________')
print('This sequence run at ', runat, mins)
print('_____________________________________________________')
print(' ')
textblock = f'This sequence run at {runat} and minutes are {mins}\n'

lookback = runat - timedelta(90)
lbdate = lookback.date()


def softwait(browser, xpath):
    print('made it to softwait')
    closebutx = "//*[contains(@type,'button')]"
    if 1 == 1:
        wait = WebDriverWait(browser, 16, poll_frequency=2,ignored_exceptions=[ElementNotVisibleException, ElementNotSelectableException])
        elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        #elem = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, xpath)))
    if 1 == 2:
        textboxes = browser.find_elements_by_xpath(xpath)
        if textboxes:
            for textbox in textboxes:
                print(f'Finding textboxes on page: {textbox.text}')
    return

def update_release(release, this_release):
    #Subroutine to update the interchange ticket Release when we have a multibooking situation, but ensure we do not change the base
    check_release = release.split('-')
    try:
        dash_num = check_release[1]
        modified_release = f'{this_release}-{dash_num}'
        return modified_release
    except:
        return this_release


def altgatescraper(dayback):

    newadd = 0
    newinterchange = []
    errors = 0
    username = usernames['gate']
    password = passwords['gate']
    print('username,password=',username,password)
    addtext = ''
    printif = 0

    outpath = addpath3('interchange/')
    print('Entering Firefox') if printif == 1 else 1
    yesterday = datetime.strftime(datetime.now() - timedelta(dayback), '%m/%d/%Y')
    todaystr = datetime.strftime(datetime.now() - timedelta(dayback), '%m/%d/%Y')
    today = datetime.today()
    cutoff = datetime.now() - timedelta(45)
    cutoff = cutoff.date()
    #todaystr = datetime.today().strftime('%m/%d/%Y')
    startdate = yesterday
    enddate = todaystr
    consets = []
    print('startdate is xxx:',yesterday)
    print('enddate is:',todaystr)

    with Display():
    #display = Display(visible=0, size=(800, 1080))
    #display.start()
    #if 1==1:
        #opts = FirefoxOptions()
        #opts.add_argument('--headless')
        logontrys = 1
        logonyes = 0
        url1 = websites['gate']

        with webdriver.Firefox() as browser:

            browser.get(url1)
            print('Got url1') if printif == 1 else 1
            time.sleep(4)
            print('Done Sleeping') if printif == 1 else 1
            print('Getting xpath') if printif == 1 else 1
            selectElem = browser.find_element_by_xpath('//*[@id="UserName"]')
            print('Got xpath for Username') if printif == 1 else 1
            selectElem.clear()
            selectElem.send_keys(username)

            selectElem = browser.find_element_by_xpath('//*[@id="Password"]')
            print('Got xpath for Password') if printif == 1 else 1
            selectElem.clear()
            selectElem.send_keys(password)
            time.sleep(1)
            selectElem.submit()

            while logontrys<4 and logonyes == 0:
                time.sleep(4)
                newurl = browser.current_url
                print('newurl=', newurl, flush=True) if printif == 1 else 1
                if 'logon' not in newurl:
                    logonyes = 1
                else:
                    print(f'Log on failed on try {logontrys}')
                logontrys += 1

            if logonyes:
                newurl = newurl+'#/Report/GateActivity'
                browser.get(newurl)
                time.sleep(4)
                print('newurl=', newurl, flush=True)

                softwait(browser, '//*[@id="StartDate"]')
                try:
                    selectElem = browser.find_element_by_xpath('//*[@id="StartDate"]')
                    selectElem.clear()
                    selectElem.send_keys(startdate)
                except:
                    print('Could not find StartDate Box')
                    errors +=1
                    addtext = addtext + f'<br>Failed to find StartDate Box for {startdate}'
                    addtext = addtext + f'<br>at url: {newurl}'
                    return addtext, newadd, newinterchange, errors

                try:
                    selectElem = browser.find_element_by_xpath('//*[@id="EndDate"]')
                    selectElem.clear()
                    selectElem.send_keys(enddate)
                    time.sleep(1)
                    selectElem.submit()
                    time.sleep(7)
                except:
                    print('Could not find Enddate Box')
                    errors +=1
                    addtext = addtext + f'<br>Failed to find EndDate Box for {enddate}'
                    addtext = addtext + f'<br>at url: {newurl}'
                    return addtext, newadd, newinterchange, errors

                try:
                    contentstr = f'//*[@id="completed"]/div/div[1]'
                    selectElem = browser.find_element_by_xpath(contentstr)
                    con = selectElem.text
                    res = [int(i) for i in con.split() if i.isdigit()]
                except:
                    res = [0]
                    print('No gate transactions reported')
                    #errors += 1
                    addtext = addtext + f'<br>No Gate Transactions Reported'
                    return addtext, newadd, newinterchange, errors

                try:
                    if len(res) > 0:
                        numrec = int(res[0])
                        print('Number of Elements in Table = ', numrec)
                    else:
                        numrec = 0
                        print('No gate transactions reported')
                        addtext = addtext + f'<br>No Gate Transactions Reported'
                        return addtext, newadd, newinterchange, errors

                except:
                    errors += 1
                    addtext = addtext + f'<br>Failed to read table that has values'
                    return addtext, newadd, newinterchange, errors


                if 1==1:
                    #try to change the number per page to 30
                    #contentstr = f'//*[@id="completed"]/div/div[4]/div/ul[1]/li/select'
                    #selectElem = browser.find_element_by_xpath(contentstr)
                    #time.sleep(1)
                    #selectElem.select_by_index(3)
                    #time.sleep(1)
                    #changed default number per page to 30 from 20...test and worked

                    conrecords = []
                    for i in range(numrec, 0, -1):
                        cr = []
                        for j in range(1,12):
                            contentstr = f'//*[@id="completed"]/div/div[3]/table/tbody/tr[{i}]/td[{j}]'
                            selectElem = browser.find_element_by_xpath(contentstr)
                            con = selectElem.text
                            if j==1:
                                movetyp = selectElem.text.strip()
                                movetyp = movetyp.replace('Full','Load')
                                movetyp = movetyp.replace('Export Dray-Off','Load Out')
                                con = movetyp
                            cr.append(con)
                            if j==3:
                                nc = browser.find_element_by_xpath(f'//*[@id="completed"]/div/div[3]/table/tbody/tr[{i}]/td[{j}]/a')
                                clink = nc.get_attribute('href')
                                cr.append(clink)
                                thiscon = selectElem.text.strip()

                        if hasinput(thiscon) and hasinput(movetyp):
                            idat = Interchange.query.filter( (Interchange.Container == thiscon) & (Interchange.Type == movetyp) & (Interchange.Date > cutoff) ).first()
                            if idat is None:
                                print(f'No interchange ticket for container {thiscon} and movetyp {movetyp}')
                            else:
                                print(f'Found record for container {thiscon} and movetyp {movetyp}')
                                conrecords.append(cr)

                        else:
                            print(f'Could not get the container or movetyp value for this record {i} of {numrec+1}')

                    for rec in conrecords:
                        thiscon = rec[2]
                        movetyp = rec[0]
                        clink = rec[3]
                        browser.get(clink)
                        time.sleep(2)

                        kdat = Interchange.query.filter((Interchange.Container == thiscon) & (Interchange.Type == movetyp) & (Interchange.Date > cutoff)).first()

                        if kdat is not None:

                            contentstr = '/html/body/table/tbody/tr[3]/td/table/tbody/tr/td[3]'
                            selectElem = browser.find_element_by_xpath(contentstr)
                            exitdt = selectElem.text
                            print(f'Exit Date-Time: {exitdt}')
                            dpt_exit = exitdt.split()
                            exit_time = dpt_exit[1]
                            print(f'Exit time: {exit_time}')

                            in_time = kdat.Time
                            print(f'In-Time is:{in_time} and Exit time: {exit_time}')
                            in_timedt = datetime.strptime(in_time, '%H:%M')
                            out_timedt = datetime.strptime(exit_time, '%H:%M')
                            # Calculate time in port
                            print(f'In Time: {in_timedt}')
                            port_time = out_timedt - in_timedt
                            port_minutes = int(port_time.seconds / 60)
                            print(f'Port Time in Minutes: {port_minutes}')

                            kdat.TimeExit = exit_time
                            kdat.PortHours = port_minutes

                            db.session.commit()

                        else:
                            print(f'No interchange ticket for {thiscon} and movetyp {movetyp}')



            else:
                print(f'Logon failed with trys = {logontrys}')
                addtext = addtext + f'Logon failed with trys = {logontrys}'

            browser.quit()

    return errors


try:
    days1 = int(sys.argv[2])
except:
    days1 = 0

try:
    days2 = int(sys.argv[3])
except:
    days2 = 0



if days2:
    if days2 > days1:
        daybackvec = list(range(days1,days2+1))
    elif days2 < days1:
        daybackvec = list(range(days1, days2-1, -1))
    else:
        daybackvec = [days1]

else:
    daybackvec = [days1]

#daybackvec = [0] #[2, 0] would run 2 days back then 0 days back, skipping 1 day back
print(f'{scac} run to update exit tiem and port time at {runat} with for daysback: {daybackvec}')
for ix in daybackvec:
    print('Running this far back:',ix)
    errors = altgatescraper(ix)

    # Update the driver from the pin database set
    #getdriver(printif,ix)

if nt == 'remote': tunnel.stop()
