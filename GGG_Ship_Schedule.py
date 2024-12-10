# This python file is run using the script ships.sh

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
from selenium.webdriver.common.action_chains import ActionChains
from utils import hasinput


#Handle the input arguments from script file
#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    nt = 'remote'
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    print('Setting SCAC to FELA since none provided')
    scac = 'fela'
    nt = 'remote'

scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running GGG_Ship_Schedule for {scac} in tunnel mode: {nt}')

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
    from models8 import Ships
    from CCC_system_setup import websites, usernames, passwords

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()


printif = 0

runat = datetime.now()
tnow = runat.strftime("%M")
mins = int(tnow)
today = runat.date()
print(' ')
print('_______________________________________________________')
print(f'This sequence run date: {today}')
print('_______________________________________________________')
print(' ')
textblock = f'This sequence run at {runat} and minutes are {mins}\n'


def softwait(browser, xpath):
    try:
        wait = WebDriverWait(browser, 16, poll_frequency=2,ignored_exceptions=[ElementNotVisibleException, ElementNotSelectableException])
        elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
    except:
        textboxes = browser.find_elements_by_xpath(xpath)
        if textboxes:
            for textbox in textboxes:
                print(f'Finding textboxes on page: {textbox.text}')
    return


browser = webdriver.Firefox()
browser.maximize_window()
url = 'https://www.portsamerica.com/our-locations/schedules/baltimore-md'
browser.get(url)
softwait(browser, '//*[@id="__next"]')

# Put page in table format
selectElem = browser.find_element_by_xpath('//*[@id="__next"]/div/div[2]/main/div[1]/section/div/div[2]/div[2]/div[2]/div[1]/div/div/div[3]/div/div[1]/label/span/div/div')
selectElem.click()


# Increase table format to 50:
softwait(browser, '//*[@id="__next"]/div/div[2]/main/div[1]/section/div/div[2]/div[2]/div[2]/div[2]/div[2]/div/div/div/select')
selectElem = browser.find_element_by_xpath('//*[@id="__next"]/div/div[2]/main/div[1]/section/div/div[2]/div[2]/div[2]/div[2]/div[2]/div/div/div/select')
selectElem = Select(browser.find_element_by_xpath('//*[@id="__next"]/div/div[2]/main/div[1]/section/div/div[2]/div[2]/div[2]/div[2]/div[2]/div/div/div/select'))
sopts = len(selectElem.options)
print(f'Found {sopts} selections')

last_height = browser.execute_script("return document.body.scrollHeight")
print(f'Current browser scroll height: {last_height}')
browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

for ix, i in enumerate(selectElem.options):
    print(ix, i.text)
selectElem.select_by_index(4)
#ActionChains(browser).move_to_element(selectElem.select_by_index(4)).click().perform()

#Now read the table data
ix = 1
while ix < 50:
    # After 30 scroll to bottom:
    tt = ['']*14
    if ix == 30:
        print(f'ix is 30 so taking time to scroll down to the bottom of page')
        browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    for jx in range(1,14):
        try:
            selectElem = browser.find_element_by_xpath(f'//*[@id="schedule_table"]/tbody/tr[{ix}]/td[{jx}]/span')
            tt[jx] = selectElem.text
        except:
            tt[jx] = None

        #print(f'For ix = {ix} and jx = {jx}, the text is {tt[jx]}')
    if tt[1] is not None:
        sdat = Ships.query.filter( (Ships.Vessel == tt[1]) & (Ships.VoyageIn == tt[4]) ).order_by(Ships.id.desc()).first()
        if sdat is None:
            print(f'Adding data for vessel {tt[1]} which is new to the schedule')
            #Then add the ship to the database
            input = Ships(Vessel=tt[1], Code=tt[2], Imports=tt[3], VoyageIn=tt[4], VoyageOut=tt[5], SSCO=tt[6], ActArrival=tt[7], GenCutoff=tt[8], RefCutoff=tt[9], HazCutoff=tt[10], EstArrival=tt[11],
                          EstDeparture=tt[12], ActDeparture=tt[13], Update=1)
            db.session.add(input)
            db.session.commit()
        else:
            #Check to see if the data has changed

            if sdat.Vessel != tt[1] or sdat.VoyageIn != tt[4] or sdat.VoyageOut != tt[5] or sdat.GenCutoff != tt[8] or sdat.EstArrival != tt[11] or sdat.EstDeparture != tt[12] or sdat.ActDeparture != tt[13]:
                # Then add the ship to the database
                update = sdat.Update
                print(f'There are changes in the Vessel schedule that require updating for Vessel {sdat.Vessel}')
                input = Ships(Vessel=tt[1], Code=tt[2], Imports=tt[3], VoyageIn=tt[4], VoyageOut=tt[5], SSCO=tt[6],
                              ActArrival=tt[7], GenCutoff=tt[8], RefCutoff=tt[9], HazCutoff=tt[10], EstArrival=tt[11],
                              EstDeparture=tt[12], ActDeparture=tt[13], Update=update+1)
                db.session.add(input)
                db.session.commit()
            else:
                print(f'Vessel {tt[1]} already on the schedule and no changes')


    ix+=1


browser.quit()
if nt == 'remote': tunnel.stop()
