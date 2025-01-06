# This python file is run using the script port.sh

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
    from models8 import Ships, Orders, Exports, Imports, PortClosed
    from CCC_system_setup import websites, usernames, passwords, addpaths, addpath3

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

lookback = runat - timedelta(90)
lbdate = lookback.date()


def softwait_id(browser, this_id):
    try:
        #wait = WebDriverWait(browser, 10, poll_frequency=2,ignored_exceptions=[ElementNotVisibleException, ElementNotSelectableException])
        wait = WebDriverWait(browser, 5)
        #elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        #elem = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
        elem = wait.until(EC.presence_of_element_located((By.ID, this_id)))
        failed = 0
    except:
        failed = 1
        print(f'Soft wait timed out')
    return failed

def softwait_xpath(browser, xpath):
    try:
        #wait = WebDriverWait(browser, 10, poll_frequency=2,ignored_exceptions=[ElementNotVisibleException, ElementNotSelectableException])
        wait = WebDriverWait(browser, 5)
        #elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        elem = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
        #elem = wait.until(EC.presence_of_element_located((By.ID, this_id)))
        failed = 0
    except:
        failed = 1
    return failed

def get_container_data(ix1,ix2):
    tt = [''] * (ix2+1)
    for ix in range(ix1,ix2+1):
        xpath = f'//*[@id="inquiries-container-availability-table"]/tbody/tr/td[{ix}]'
        try:
            selectElem = browser.find_element_by_xpath(xpath)
            tt[ix] = selectElem.text
        except:
            tt[ix] = None
    return tt

def get_vessel_data(ix1,ix2):
    tt = [''] * (ix2+1)
    for ix in range(ix1,ix2+1):
        xpath = f'/html/body/div[5]/div/div/div[2]/main/div[1]/section/div/div[2]/div/div[4]/div/div[3]/div/div/table/tbody/tr[2]/td/div[1]/div[2]/div/table/tbody/tr/td[{ix}]'
        try:
            selectElem = browser.find_element_by_xpath(xpath)
            tt[ix] = selectElem.text
        except:
            tt[ix] = None
    return tt

def get_booking_data(ix1,ix2):
    tt = [''] * (ix2+1)
    for ix in range(ix1,ix2+1):
        xpath = f'/html/body/div[5]/div/div/div[2]/main/div[1]/section/div/div[2]/div/div[4]/div/div[3]/div/div/table/tbody/tr[2]/td/div[2]/div[2]/div/table/tbody/tr/td[{ix}]'
        try:
            selectElem = browser.find_element_by_xpath(xpath)
            tt[ix] = selectElem.text
        except:
            tt[ix] = None
    return tt

def check_BOL(browser, BOL):
    url = f'https://www.portsamerica.com/resources/inquiries?location=SGT_BAL&option=containerByBol&numbers={BOL}'
    browser.get(url)
    this_id = "inquiries-bol-availability-table"
    failed = softwait_id(browser, this_id)
    if failed: return 0, None
    else:
        xpath = '//*[@id="inquiries-bol-availability-table"]/tbody/tr/td[3]'
        try:
            selectElem = browser.find_element_by_xpath(xpath)
            SSCO = selectElem.text
            return 1, SSCO
        except:
            SSCO = None
            return 0, SSCO

def next_business_day(date, jx):
    next_day = date
    kx = 0
    for ix in range(15):
        next_day = next_day + timedelta(days=1)
        pdat = PortClosed.query.filter(PortClosed.Date==next_day).first()
        if pdat is None:
            kx += 1
            if kx == jx: return next_day


def import_add(jo, BOL, tt, update_version, verified, ssfile):
    if tt[2] is None: ready = 0
    elif 'y' in tt[2]: ready = 1
    else: ready = 0
    vessel, voyage = tt[14].split("/")
    input = Imports(Jo = jo, BOL=BOL, Verified=verified, Ready = ready, Container=tt[3], LineStatus=tt[4], CustomsStatus=tt[5], OtherHolds=tt[6], Location=tt[7], Position=tt[8], PTD=tt[9], LFD=tt[10], TermDem=tt[11], NonDem=tt[12], Size=tt[13], Vessel=vessel, Voyage=voyage,
                    Update=update_version, Active=1, Screen=ssfile)
    db.session.add(input)
    db.session.commit()
    return

def import_add_temp(jo, BOL, container):
    input = Imports(Jo = jo, BOL=BOL, Verified=0, Ready = 0, Container=container, LineStatus='NOF', CustomsStatus='NOF', OtherHolds='NOF', Location='NOF', Position='NOF', PTD='NOF', LFD='NOF', TermDem='NOF', NonDem='NOF', Size='NOF', Vessel='NOF', Voyage='NOF',
                    Update=1, Active=1, Screen='NOF')
    db.session.add(input)
    db.session.commit()
    return

def import_update_check(BOL, idat, tt):
    if tt[2] is None: ready = 0
    elif 'y' in tt[2]: ready = 1
    else: ready = 0
    vessel, voyage = tt[14].split("/")
    if idat.BOL != BOL: return 1
    if idat.Ready != ready: return 1
    if idat.LineStatus != tt[4] or idat.CustomsStatus != tt[5] or idat.OtherHolds != tt[6]: return 1
    if idat.Location != tt[7] or idat.Position != tt[8]: return 1
    if idat.PTD != tt[9] or idat.LFD != tt[10] or idat.TermDem != tt[11] or idat.NonDem != tt[12]: return 1
    if idat.Size != tt[13] or idat.Vessel != vessel or idat.Voyage != voyage: return 1

    return 0

def export_add(jo, booking, vs, bk, update_version, ssfile):
    # If None value for integers, make them zero:
    input = Exports(Jo=jo, Booking=booking, SSCO=vs[1], Vessel=vs[2], Voyage=vs[3], EmptyStart=vs[4], GeneralBR=vs[5], ReeferBR=vs[6], HazBR=vs[7], GeneralCut=vs[8], ReeferCut=vs[9], HazCut=vs[10], LoadingAt=vs[11], Length=bk[1],
                    Type=bk[2], Height=bk[3], Total=bk[4], Received=bk[5], Delivered=bk[6], Update=update_version, Active=1, Screen=ssfile)
    db.session.add(input)
    db.session.commit()
    return

def export_add_temp(jo, booking):
    # If None value for integers, make them zero:
    input = Exports(Jo=jo, Booking=booking, SSCO='NOF', Vessel='NOF', Voyage='NOF', EmptyStart='NOF', GeneralBR='NOF', ReeferBR='NOF', HazBR='NOF', GeneralCut='NOF', ReeferCut='NOF', HazCut='NOF', LoadingAt='NOF', Length='NOF',
                    Type='NOF', Height='NOF', Total='NOF', Received='NOF', Delivered='NOF', Update=1, Active=1, Screen='NOF')
    db.session.add(input)
    db.session.commit()
    return

def export_update_check(edat, vs, bk):
    if edat.SSCO != vs[1] or edat.Vessel != vs[2] or edat.Voyage != vs[3]: return 1
    if edat.EmptyStart != vs[4] or edat.GeneralBR != vs[5] or edat.ReeferBR != vs[6] or edat.HazBR != vs[7]: return 1
    if edat.GeneralCut != vs[8] or edat.ReeferCut != vs[9] or edat.HazCut != vs[10]: return 1
    if edat.LoadingAt != vs[11] or edat.Length != bk[1] or edat.Type != bk[2] or edat.Height != bk[3]: return 1
    if bk[4] is None or bk[5] is None or bk[6] is None: return 1
    if edat.Total != int(bk[4]) or edat.Received != int(bk[5]) or edat.Delivered != int(bk[6]): return 1
    return 0

def order_update_import(ord,jo,verified,ssco):
    hstat = ord.Hstat
    print(f'Updating import :{ord.Jo}: with hstat {hstat} and jo :{jo}: and ssco {ssco}')
    #Things to update if container still in port
    if hstat < 1:
        good_for_update = 1
        impdat = Imports.query.filter(Imports.Jo == jo).order_by(Imports.id.desc()).first()
        if impdat is None:
            #There may have been a JO update
            container = ord.Container
            impdat = Imports.query.filter(Imports.Container == container).order_by(Imports.id.desc()).first()
            if impdat is not None:
                impdat.Jo = jo
            else:
                print(f'**** There is an issue in the imports data, no match to the order data on jo or container')
                good_for_update = 0
        if good_for_update:
            vessel = impdat.Vessel
            vessel = vessel.strip()
            voyage = impdat.Voyage
            voyage = voyage.strip()
            ship = Ships.query.filter((Ships.Vessel==vessel) & (Ships.VoyageIn == voyage)).order_by(Ships.id.desc()).first()
            if ship is not None:
                arrival = ship.ActArrival
                if arrival is not None: arrival = arrival.strip()
                if arrival is None: arrival = ship.EstArrival
                arrival = arrival.split(' ', 1)[0]
                print(f'Converting arrival date time ::{arrival}:: for vessel {vessel}')
                arrival = datetime.strptime(arrival, "%m/%d/%Y")
                arrival = arrival.date()
                avail_at_port = next_business_day(arrival, 1)

                lfd = impdat.LFD
                lfd = lfd.strip()
                if lfd == '' or lfd == 'NOF':
                    lfd = next_business_day(avail_at_port, 3)
                else:
                    print(f'Converting lfd date time ::{lfd}::')
                    lfd = datetime.strptime(lfd, "%m/%d/%Y")
                    lfd = lfd.date()
                ord.Date4 = avail_at_port
                ord.Date5 = lfd
                ord.Date6 = arrival
                print(f'Update Order: Date4:{avail_at_port} Date5:{lfd} Date6:{arrival}')
                planned_gate_out = ord.Date
                planned_delivery = ord.Date3
                planned_return = ord.Date2
                if planned_gate_out < avail_at_port: ord.Date = avail_at_port
                if planned_delivery < avail_at_port:
                    #Change delivery date, but only if the date has not been set manually/hard
                    if ord.Status != 'MSD': ord.Date3 = avail_at_port
                if planned_return < avail_at_port: ord.Date2 = avail_at_port + timedelta(days=1)

                if verified:
                    ord.Status = 'VER'
                    ord.SSCO = ssco
                    ord.Ship = vessel
                    ord.Voyage = voyage

                db.session.commit()


        else:
            print(f'Could not find Vessel:{vessel}: and Voyage:{voyage}:')
            # Need to set state for a future update once vessel appears:
            ord.Status = 'SNF'
            ord.SSCO = ssco
            ord.Ship = vessel
            ord.Voyage = voyage
            db.session.commit()




    #Things to update only if container is out of port
    if hstat == 1:
        gate_out = ord.Date
        due_back = next_business_day(gate_out,3)
        ord.Date7 = due_back
        db.session.commit()

    return


def order_update_export(ord,jo):
    hstat = ord.Hstat
    status = ord.Status

    #Things to update if container still in port
    if hstat < 1:
        expdat = Exports.query.filter(Exports.Jo == jo).order_by(Exports.id.desc()).first()
        vessel = expdat.Vessel
        vessel = vessel.strip()
        voyage = expdat.Voyage
        voyage = voyage.strip()
        erd = expdat.GeneralBR
        cut = expdat.GeneralCut
        erd = erd.strip()
        cut = cut.strip()
        ssco = expdat.SSCO
        if erd == '' or erd == 'NOF': erd = 'NOF'
        if cut == '' or cut == 'NOF': cut = 'NOF'

        #In this case the booking is not in the system
        if vessel == 'NOF' and erd == 'NOF' and cut == 'NOF':
            ord.Date4 = None
            ord.Date5 = None
            ord.Date6 = None
            db.session.commit()
            return

        else:
            if erd != 'NOF':
                erd = erd.split(' ', 1)[0]
                print(f'Converting erd date time ::{erd}::')
                erd = datetime.strptime(erd, "%m/%d/%Y")
                erd = erd.date()
                ord.Date4 = erd
                print(f'Updated Order: Date4:{erd}')
            if cut != 'NOF':
                cut = cut.split(' ', 1)[0]
                print(f'Converting cut date time ::{cut}::')
                cut = datetime.strptime(cut, "%m/%d/%Y")
                cut = cut.date()
                ord.Date5 = cut
                print(f'Updated Order: Date5:{cut}')

            ord.Status = 'AOK'
            ord.SSCO = ssco
            ord.Ship = vessel
            ord.Voyage = voyage
            db.session.commit()

        ship = Ships.query.filter((Ships.Vessel==vessel) & (Ships.VoyageIn == voyage)).order_by(Ships.id.desc()).first()
        if ship is not None:
            arrival = ship.ActArrival
            if arrival is not None: arrival = arrival.strip()
            else: arrival = ''
            if arrival == '': arrival = ship.EstArrival
            arrival = arrival.split(' ', 1)[0]
            print(f'Converting arrival date time ::{arrival}::')
            arrival = datetime.strptime(arrival, "%m/%d/%Y")
            #arrival = datetime.strptime(arrival, "%m/%d/%Y %H:%M")
            arrival = arrival.date()
            ord.Date6 = arrival
            ord.Ship = vessel
            ord.Voyage = voyage
            ord.Status = 'VER'
            db.session.commit()
            print(f'Updated Order Date6:{arrival}')
        else:
            ord.Ship = vessel
            ord.Voyage = voyage
            ord.Status = 'SNF'
            db.session.commit()


    #Things to update only if container is out of port
    if hstat == 1:
        gate_out = ord.Date
        due_back = next_business_day(gate_out,3)
        ord.Date7 = due_back

        expdat = Exports.query.filter(Exports.Jo == jo).order_by(Exports.id.desc()).first()
        vessel = expdat.Vessel
        vessel = vessel.strip()
        voyage = expdat.Voyage
        voyage = voyage.strip()
        erd = expdat.GeneralBR
        cut = expdat.GeneralCut
        erd = erd.strip()
        cut = cut.strip()
        olderd = ord.Date4
        oldcut = ord.Date5
        if erd == '' or erd == 'NOF': erd = 'NOF'
        if cut == '' or cut == 'NOF': cut = 'NOF'
        if erd != 'NOF':
            erd = erd.split(' ', 1)[0]
            print(f'Converting erd date time ::{erd}::')
            erd = datetime.strptime(erd, "%m/%d/%Y")
            erd = erd.date()
            ord.Date4 = erd
            if olderd is not None:
                if olderd != erd: print(f'****Alert*** the ERD has shifted from {olderd} to {erd}')
        if cut != 'NOF':
            cut = cut.split(' ', 1)[0]
            print(f'Converting cut date time ::{cut}::')
            cut = datetime.strptime(cut, "%m/%d/%Y")
            cut = cut.date()
            ord.Date5 = cut
            if oldcut is not None:
                if oldcut != cut: print(f'****Alert*** the CUTOFF has shifted from {oldcut} to {cut}')
        db.session.commit()

    return


def con_check(con_len, order_con_type):
    print(f'The container size check is: {con_len}, {order_con_type}')

    if '40' in con_len:
        if '40' in order_con_type:
            print(f'The container size check  for 40s good: {con_len}, {order_con_type}')
        elif '20' in order_con_type:
            print(f'The container size check  for 40s bad order has a 20: {con_len}, {order_con_type}')
        elif '45' in order_con_type:
            print(f'The container size check  for 40s bad order has a 45: {con_len}, {order_con_type}')
        else:
            print(f'The container size check  for 40s bad unknown why: {con_len}, {order_con_type}')
    if '20' in con_len:
        if '20' in order_con_type:
            print(f'The container size check  for 20s good: {con_len}, {order_con_type}')
        elif '40' in order_con_type:
            print(f'The container size check  for 20s bad order has a 40: {con_len}, {order_con_type}')
        elif '45' in order_con_type:
            print(f'The container size check  for 20s bad order has a 45: {con_len}, {order_con_type}')
        else:
            print(f'The container size check  for 20s bad unknown why: {con_len}, {order_con_type}')
    if '45' in con_len:
        if '45' in order_con_type:
            print(f'The container size check  for 45s good: {con_len}, {order_con_type}')
        elif '40' in order_con_type:
            print(f'The container size check  for 45s bad order has a 40: {con_len}, {order_con_type}')
        elif '20' in order_con_type:
            print(f'The container size check  for 45s bad order has a 20: {con_len}, {order_con_type}')
        else:
            print(f'The container size check  for 45s bad unknown why: {con_len}, {order_con_type}')



############################################################################################################################################
#IMPORTS Section to check on containers that have not been pulled yet
#############################################################################################################################################
good_con = 0
while good_con < 4:
    try:
        imports = Orders.query.filter(Orders.HaulType.contains('Import') & (Orders.Hstat < 2) & (Orders.Date3 > lbdate)).all()
        good_con = 8
    except:
        good_con += 1
        print(f'Connection try again number {good_con}')

if good_con == 8:
    browser = webdriver.Firefox()
    browser.maximize_window()
    for imp in imports:
        jo = imp.Jo
        container = imp.Container
        BOL = imp.Booking
        tdate = imp.Date3
        status = imp.Status
        ssco = imp.SSCO
        print(f'Getting data for JO {jo} import container {container} that has date of {tdate} has ssco :{ssco}:')
        url = f'https://www.portsamerica.com/resources/inquiries?location=SGT_BAL&option=containerByContainer&numbers={container}'
        browser.get(url)
        #xpath = '//*[@id="mantine-m2hfnicq9-panel-container"]/div/div[1]/div[4]/button[1]/span/span'
        #xpath = '//*[@id="mantine-m2hfnicq9-panel-container"]'
        this_id = "inquiries-container-availability-table"
        failed = softwait_id(browser, this_id)
        if not failed:
            con_data = get_container_data(2, 14)
            print(con_data)
            idat = Imports.query.filter((Imports.Container == container) & (Imports.Active == 1)).order_by(Imports.id.desc()).first()

            if idat is None:
                # The job is not in the import database yet, but has a successful find in the port data
                update_version = 1
                ssfilebase = f'{container}_{today}.png'
                ssfile = addpath3(f'{scac}/{ssfilebase}')
                browser.get_screenshot_as_file(ssfile)
                copyline = f'scp {ssfile} {websites["ssh_data"] + "vPort"}'
                print('copyline=', copyline)
                os.system(copyline)
                verified, ssco = check_BOL(browser, BOL)
                import_add(jo, BOL, con_data, update_version, verified, ssfilebase)
                order_update_import(imp,jo,verified,ssco)
                con_len = con_data[13]
                order_con_type = imp.Type
                con_check(con_len, order_con_type)


            else:
                # The job is in the import database yet, and has a successful find in the port data
                # See if an update is required:
                update_needed = import_update_check(BOL, idat, con_data)
                if update_needed:
                    update_version = idat.Update + 1
                    ssfilebase = f'{container}_{today}.png'
                    ssfile = addpath3(f'{scac}/{ssfilebase}')
                    browser.get_screenshot_as_file(ssfile)
                    copyline = f'scp {ssfile} {websites["ssh_data"] + "vPort"}'
                    print('copyline=', copyline)
                    os.system(copyline)
                    verified, ssco = check_BOL(browser, BOL)
                    import_add(jo, BOL, con_data, update_version, verified, ssfilebase)
                elif status == 'SNF' or not hasinput(ssco):
                    verified, ssco = check_BOL(browser, BOL)
                    print(f'For SNF block: {verified}, {ssco}')
                else:
                    verified = 0
                order_update_import(imp, jo, verified, ssco)


        else:
            # The job is not yet of file at port
            # See if already in the import database:
            checkimp = Imports.query.filter(Imports.Jo == jo).first()
            if checkimp is None:
                import_add_temp(jo, BOL, container)
            else:
                checkimp.Verified = 0
                db.session.commit()
            # Report the container not on file yet


    browser.quit()
    #############################################################################################################################################

    ############################################################################################################################################
    #EXPORTS Section to check on bookings that have not been pulled or returned
    #############################################################################################################################################
    good_con = 0
    while good_con < 4:
        try:
            exports = Orders.query.filter(Orders.HaulType.contains('Export') & (Orders.Hstat < 2) & (Orders.Date3 > lbdate)).all()
            good_con = 5
        except:
            good_con += 1
            print(f'Connection try again number {good_con}')

    browser = webdriver.Firefox()
    browser.maximize_window()
    for exp in exports:
        jo = exp.Jo
        status = exp.Status
        booking = exp.Booking
        booking = booking.split('-', 1)[0]
        tdate = exp.Date3
        print(f'Getting data for export booking {booking} for date {tdate}')
        url = f'https://www.portsamerica.com/resources/inquiries?location=SGT_BAL&option=bookingInquiry&numbers={booking}'
        browser.get(url)
        #xpath = '//*[@id="mantine-m2hfnicq9-panel-container"]/div/div[1]/div[4]/button[1]/span/span'
        #xpath = '//*[@id="mantine-m2hfnicq9-panel-container"]'
        this_id = "inquiries-booking-table"
        softwait_id(browser, this_id)
        print(f'Completed soft wait for export booking {booking}')
        #selectElem = browser.find_element_by_xpath('//*[@id="inquiries-booking-table"]/tbody/tr/td[1]/button/div/span')
        #selectElem.click()
        #vessel_xpath = '/html/body/div[1]/div/div/div[2]/main/div[1]/section/div/div[2]/div/div[4]/div/div[3]/div/div/table/tbody/tr[2]/td/div[1]/div[2]/div/table/tbody/tr/td[1]'
        #vessel_xpath = '//*[@id="inquiries-booking-vessel-info-table - 0}"]/tbody/tr/td[1]'
        vessel_xpath = '/html/body/div[5]/div/div/div[2]/main/div[1]/section/div/div[2]/div/div[4]/div/div[3]/div/div/table/tbody/tr[2]/td/div[1]/div[2]/div/table/tbody/tr/td[1]'

        failed = softwait_xpath(browser, vessel_xpath)
        if not failed:
            vs_data = get_vessel_data(1, 11)
            print(vs_data)
            bk_data = get_booking_data(1,6)
            print(bk_data)

            edat = Exports.query.filter((Exports.Booking == booking) & (Exports.Jo == jo) & (Exports.Active == 1)).order_by(Exports.id.desc()).first()

            if edat is None:
                update_version = 1
                ssfilebase = f'{booking}_{today}.png'
                ssfile = addpath3(f'{scac}/{ssfilebase}')
                browser.get_screenshot_as_file(ssfile)
                copyline = f'scp {ssfile} {websites["ssh_data"] + "vPort"}'
                print('copyline=', copyline)
                os.system(copyline)
                export_add(jo, booking, vs_data, bk_data, update_version, ssfilebase)
                order_update_export(exp, jo)

            else:
                update_needed = export_update_check(edat, vs_data, bk_data)
                if update_needed:
                    update_version = edat.Update + 1
                    ssfilebase = f'{booking}_{today}.png'
                    ssfile = addpath3(f'{scac}/{ssfilebase}')
                    browser.get_screenshot_as_file(ssfile)
                    copyline = f'scp {ssfile} {websites["ssh_data"] + "vPort"}'
                    print('copyline=', copyline)
                    os.system(copyline)
                    export_add(jo, booking, vs_data, bk_data, update_version, ssfilebase)
                order_update_export(exp, jo)
                #if status == 'SNF': order_update_export(exp, jo)

            con_len = bk_data[1]
            order_con_type = exp.Type
            con_check(con_len, order_con_type)


        else:
            print(f'Failed to find export booking {booking}')
            # The booking is not yet of file at port
            # See if already in the export database:
            checkexp = Exports.query.filter(Exports.Jo == jo).first()
            if checkexp is None:
                export_add_temp(jo, booking)
            else:
                checkexp.Verified = 0
                db.session.commit()
            db.session.commit()
            # Report the booking not on file yet
    #############################################################################################################################################

    browser.quit()

    # Now clear up the import and export database for runs that have been completed..make them inactive 5 days after completion.
    importx = Orders.query.filter(Orders.HaulType.contains('Import') & (Orders.Hstat > 1) & (Orders.Date3 > lbdate)).all()
    exportx = Orders.query.filter(Orders.HaulType.contains('Export') & (Orders.Hstat > 1) & (Orders.Date3 > lbdate)).all()
    for impx in importx:
        jo = impx.Jo
        gatein = impx.Date2
        lapse = today - gatein
        lapse = lapse.days
        impdat = Imports.query.filter(Imports.Jo == jo).order_by(Imports.id.desc()).first()
        if impdat is not None and lapse > 5:
            impdat.Active = 0
            db.session.commit()


    for expx in exportx:
        jo = expx.Jo
        gatein = expx.Date2
        lapse = today - gatein
        lapse = lapse.days
        expdat = Exports.query.filter(Exports.Jo == jo).order_by(Exports.id.desc()).first()
        if expdat is not None and lapse > 5:
            expdat.Active = 0
            db.session.commit()




if nt == 'remote': tunnel.stop()

