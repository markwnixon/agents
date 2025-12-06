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
    scac2 = sys.argv[2]
    container = sys.argv[3]
    nt = 'remote'
    print(f'Received input argument of SCAC: {scac}')
    print(f'Will transfer into the system for SCAC: {scac2}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    print('Setting SCAC to FELA since none provided')
    scac = 'fela'
    scac2= 'oslm'
    container = 'TEMU6350552'
    nt = 'remote'

scac = scac.upper()
scac2 = scac2.upper()

if scac == 'FELA': company = 'FIRST EAGLE LOGISTICS, INC.'
if scac == 'OSLM': company = 'ONE STOP LOGISTICS'
if scac == 'NEVO': company = 'NELLO ENTERPRISE LLC'
if scac2 == 'FELA': company2 = 'FIRST EAGLE LOGISTICS, INC.'
if scac2 == 'OSLM': company2 = 'ONE STOP LOGISTICS'
if scac2 == 'NEVO': company2 = 'NELLO ENTERPRISE LLC'


if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':

    print(f'Running FFF_Gate_Shuttle for {scac} in tunnel mode: {nt}')
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

idata = Interchange.query.filter((Interchange.Container == container) & (Interchange.Date >= lbdate)).all()
sh = []
for idat in idata:
    sh.append({'Date':idat.Date, 'Container':idat.Container, 'Type':idat.Type, 'Chassis':idat.Chassis, 'html':''})
print(sh)

#Next find the data for each container and save the html file



def get_driver(movetyp,finder):
    driver = 'Unfound'
    if movetyp == 'Load Out':
        # finder is OutCon
        pdat = Pins.query.filter(Pins.OutCon == finder).order_by(Pins.id.desc()).first()
        if pdat is not None:
            return pdat.Driver
    if movetyp == 'Empty Out':
        # finder is OutCon
        pdat = Pins.query.filter(Pins.OutBook == finder).order_by(Pins.id.desc()).first()
        if pdat is not None:
            return pdat.Driver
    if movetyp == 'Empty In':
        # finder is OutCon
        pdat = Pins.query.filter(Pins.InCon == finder).order_by(Pins.id.desc()).first()
        if pdat is not None:
            return pdat.Driver
    if movetyp == 'Load In':
        # finder is OutCon
        pdat = Pins.query.filter(Pins.InCon == finder).order_by(Pins.id.desc()).first()
        if pdat is not None:
            return pdat.Driver
    return driver


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

def blendticks(gfile1,gfile2,outfile):

    reader1 = PdfReader(open(gfile1, 'rb'))
    p1 = reader1.pages[0]

    reader2 = PdfReader(open(gfile2, 'rb'))
    p2 = reader2.pages[0]

    paths = addpaths()
    thispath = paths[3]
    g3 = f'{thispath}blank.pdf'
    print(f'g3={g3}')

    reader3 = PdfReader(open(g3, 'rb'))
    p3 = reader3.pages[0]
    #p2.cropBox.lowerLeft = (50,400)
    #p2.cropBox.upperRight = (600,700)
    #translate first page
    p1.add_transformation(Transformation().translate(tx=0, ty=-80))
    p3.merge_page(p1)


    #offset_x = p2.mediaBox[2]
    offset_x = 0
    #offset_y = -280
    offset_y = -325

    # add second page to first one
    p2.add_transformation(Transformation().translate(tx=offset_x, ty=offset_y))
    p3.merge_page(p2)
    p3.cropbox.lower_left = (50, 150)
    p3.cropbox.upper_right = (550,800)

    output = PdfWriter()
    output.add_page(p3)

    with open(outfile, "wb") as out_f:
        output.write(out_f)

def wait_for_file(filename, timeout=45):
    """Waits for a file to be created, with a timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if os.path.exists(filename):
            return True
        time.sleep(1)
    return False

def make_blended(odat,ingate,outgate):
    # Make blended tickets for this matched container
    con = odat.Container
    jo = odat.Jo
    gate = odat.Gate
    pdf1 = ingate.Source
    pdf2 = outgate.Source
    test = 0
    if con in pdf1 and con in pdf2 and 'OUT' in pdf1 and ('IN' in pdf2 or 'Source' in pdf2): test = 1
    print(f'In make_blended for order {jo} we have container {con} and pdf files {pdf1} and {pdf2} and test is {test}')
    if test == 1:
        blendfile = f'{con}_Blended.pdf'
        scp_path = f'{websites["ssh_data"] + "vGate/"}'
        scpfile = scp_path + blendfile
        tempfile = addpath3(f'{scac}/{blendfile}')
        tempfile1 = addpath3(f'{scac}/{pdf1}')
        tempfile2 = addpath3(f'{scac}/{pdf2}')
        print(f'scac is {scac} and pdf1 is {pdf1} and pdf2 is {pdf2}')
        print(f'********tempfile1 is {tempfile1}')
        print(f'********tempfile2 is {tempfile2}')

        #Check to see if we have a local copy.  May need to get from remote if running this script multiple locations
        #if not os.path.isfile(tempfile1): tempfile1 = check_remote(tempfile1)
        #if not os.path.isfile(tempfile2): tempfile2 = check_remote(tempfile2)

        scpcom = f'scp {scpfile} {tempfile}'
        scpcom1 = f'scp {scp_path}{pdf1} {tempfile1}'
        scpcom2 = f'scp {scp_path}{pdf2} {tempfile2}'

        newdoc = f'static/{scac}/data/vGate/{con}_Blended.pdf'
        print(f'The blended file is: {blendfile}')

        try:
            os.system(scpcom)
        except:
            print('The blended_file does not exist')
        try:
            os.system(scpcom1)
        except:
            print(f'Could not get file {pdf1} from remote site')
        try:
            os.system(scpcom2)
        except:
            print(f'Could not get file {pdf2} from remote site')

        if os.path.isfile(tempfile):
            print(f'{blendfile} exists already')
            print(f'Remaking {blendfile}')
            odat.Gate = f'{con}_Blended.pdf'
            db.session.commit()

        if os.path.isfile(tempfile1) and os.path.isfile(tempfile2):
            print(f'Have the temp files needed to make blended and will place in database if successful')
            blendticks(tempfile1, tempfile2, tempfile)
            odat.Gate = f'{con}_Blended.pdf'
            db.session.commit()

            if wait_for_file(tempfile):
                print(f"{tempfile} has been created.")
            else:
                print(f"Timeout waiting for {tempfile}.")

            if os.path.isfile(tempfile):
                copyline = f'scp {tempfile} {websites["ssh_data"] + "vGate"}'
                print('copyline=', copyline)
                os.system(copyline)
                os.remove(tempfile1)
                os.remove(tempfile2)
                os.remove(tempfile)
            else:
                print('The blended file was not created successfully')
        else:
            if not os.path.isfile(tempfile1): print(f'Do not have tempfile1:{tempfile1}')
            if not os.path.isfile(tempfile2): print(f'Do not have tempfile2:{tempfile2}')

def update_release(release, this_release):
    #Subroutine to update the interchange ticket Release when we have a multibooking situation, but ensure we do not change the base
    check_release = release.split('-')
    try:
        dash_num = check_release[1]
        modified_release = f'{this_release}-{dash_num}'
        return modified_release
    except:
        return this_release

def update_records(thiscon, id):
    print(f'Updating database records for container {thiscon} and Interchange id {id}')
    ikat = Interchange.query.get(id)
    if ikat is not None:
        con = ikat.Container
        release = ikat.Release
        movetyp = ikat.Type

        if movetyp == 'Load Out':
            #This should be an import, container will already be edited input
            okat = Orders.query.filter(Orders.Container==thiscon).order_by(Orders.id.desc()).first()
            driver = get_driver(movetyp, con)
            if okat is not None:
                ikat.Jo = okat.Jo
                ikat.Status = 'Out'
                ikat.Company = okat.Shipper
                ikat.Driver = driver
                okat.Chassis = ikat.Chassis
                okat.ConType = ikat.ConType
                okat.Date = ikat.Date
                okat.Hstat = 1
                db.session.commit()

        if movetyp == 'Empty Out':
            #This should be an export, container number needs to be created.
            #However, we could be part of multiple bookings so we need to check on which one this is
            edata = Orders.query.filter((Orders.HaulType.contains('Export')) & (Orders.Booking.contains(release)) & (Orders.Date > lbdate)).all()
            nbk = len(edata)
            multibooking = 0
            if nbk > 1:
                # Check to make sure they all have the same base booking.
                bk_multibook = []
                for edat in edata:
                    tbooking = edat.Booking
                    tbklist = tbooking.split('-')
                    tbook = tbklist[0]
                    if tbook == release:
                        multibooking += 1
                        hstat = edat.Hstat
                        if hstat < 1:
                            bk_multibook.append(edat.Booking)
                if multibooking > 1:
                    # Reorder the multi-book bookings
                    if bk_multibook != []:
                        bk_multibook.sort()
                        first_unpulled_release = bk_multibook[0]
                        eck = Orders.query.filter((Orders.HaulType.contains('Export')) & (Orders.Booking == first_unpulled_release) & (Orders.Date > lbdate)).first()
                        if eck is not None:
                            container = eck.Container
                            if not hasinput(container):
                                release = eck.Booking
                                print(f'The first unpulled booking on multibooking {first_unpulled_release} has no container and will be updated.')
                            else:
                                print(f'The first unpulled booking on multibooking {first_unpulled_release} already has a container assigned: {container}')

            okat = Orders.query.filter(Orders.Booking == release).order_by(Orders.id.desc()).first()
            driver = get_driver(movetyp, release)
            if okat is not None:
                ikat.Jo = okat.Jo
                ikat.Status = 'Out'
                ikat.Company = okat.Shipper
                ikat.Driver = driver
                #This is to make sure we do not overwrite the base release of the multibooking
                if multibooking > 1:
                    this_release = ikat.Release
                    ikat.Release = update_release(release, this_release)
                okat.Container = con
                okat.ConType = ikat.ConType
                okat.Chassis = ikat.Chassis
                okat.Date = ikat.Date
                okat.Hstat = 1
                db.session.commit()

        if movetyp == 'Empty In':
            #This should be an import return
            okat = Orders.query.filter(Orders.Container==thiscon).order_by(Orders.id.desc()).first()
            driver = get_driver(movetyp, con)
            if okat is not None:
                ikat.Jo = okat.Jo
                ikat.Company = okat.Shipper
                ikat.Driver = driver
                okat.Chassis = ikat.Chassis
                okat.Date2 = ikat.Date
                okat.Hstat = 2
                db.session.commit()
            imat = Interchange.query.filter( (Interchange.Container == thiscon) & (Interchange.Type.contains('Out')) & (Interchange.Date > lbdate)).first()
            if imat is not None:
                ikat.Status = 'IO'
                imat.Status = 'IO'
                db.session.commit()
                make_blended(okat,imat,ikat)
            else:
                print(f'Could not find a match for the Empty in container {thiscon}')
                ikat.Status = 'No Out'

        if movetyp == 'Load In':
            #This should be an export return
            okat = Orders.query.filter(Orders.Container == thiscon).order_by(Orders.id.desc()).first()
            #okat = Orders.query.filter(Orders.Container==thiscon).first()
            driver = get_driver(movetyp, con)
            if okat is not None:
                #inbook = okat.BOL
                #if not hasinput(inbook): inbook = okat.Booking
                #if len(inbook) < 4: inbook = okat.Booking
                #print(f'******************the in booking for {thiscon} with type {movetyp} is **{inbook}*************')
                ikat.Jo = okat.Jo
                ikat.Company = okat.Shipper
                ikat.Driver = driver
                okat.Chassis = ikat.Chassis
                okat.Date2 = ikat.Date
                okat.Hstat = 2
                okat.BOL = release
                db.session.commit()
            imat = Interchange.query.filter( (Interchange.Container == thiscon) & (Interchange.Type.contains('Out')) & (Interchange.Date > lbdate)).first()
            if imat is not None:
                ikat.Status = 'IO'
                imat.Status = 'IO'
                db.session.commit()
                make_blended(okat,imat,ikat)
            else:
                print(f'Could not find a match for the load in container {thiscon}')
                ikat.Status = 'No Out'

    return 'Success'



def moveticks(gfile1,outfile):

    reader1 = PdfFileReader(open(gfile1, 'rb'))
    p1 = reader1.getPage(0)

    #reader2 = PdfFileReader(open(gfile1, 'rb'))
    #p2 = reader2.getPage(0)
    #p2.cropBox.lowerLeft = (50,400)
    #p2.cropBox.upperRight = (600,700)

    #offset_x = p2.mediaBox[2]
    offset_x = 0
    offset_y = -280

    # add second page to first one
    #p1.mergeTranslatedPage(p2, offset_x, offset_y, expand=False)
    p1.cropBox.lowerLeft = (50,250)
    p1.cropBox.upperRight = (550,800)

    output = PdfFileWriter()
    output.addPage(p1)

    with open(outfile, "wb") as out_f:
        output.write(out_f)

def getdriver(printif, dayback):
    cutoff = datetime.now() - timedelta(30)
    cutoff = cutoff.date()
    idata = Interchange.query.filter((Interchange.Driver == 'NAY')  & (Interchange.Date > cutoff)).all()
    for idat in idata:
        con = idat.Container
        type = idat.Type
        book = idat.Release
        if type == 'Load In': pdat = Pins.query.filter((Pins.InCon == con) & (Pins.Date > cutoff)).first()
        if type == 'Load Out': pdat = Pins.query.filter((Pins.OutCon == con) & (Pins.Date > cutoff)).first()
        if type == 'Empty Out': pdat = Pins.query.filter((Pins.OutBook == book) & (Pins.Date > cutoff)).first()
        if type == 'Empty In': pdat = Pins.query.filter((Pins.InCon == con) & (Pins.Date > cutoff)).first()
        if pdat is not None:
            driver = pdat.Driver
            idat.Driver = driver
        db.session.commit()


def gatescraper(printif, s):

    newadd = 0
    newinterchange = []
    errors = 0
    username = usernames['gate']
    password = passwords['gate']
    print('username,password=',username,password)
    addtext = ''

    godate = s['Date']
    confind = s['Container']
    typefind = s['Type']

    outpath = addpath3('interchange/')
    print('Entering Firefox') if printif == 1 else 1
    yesterday = datetime.strftime(godate - timedelta(1), '%m/%d/%Y')
    todaystr = datetime.strftime(godate, '%m/%d/%Y')
    today = datetime.today()
    cutoff = datetime.now() - timedelta(45)
    cutoff = cutoff.date()
    #todaystr = datetime.today().strftime('%m/%d/%Y')
    startdate = yesterday
    enddate = todaystr
    consets = []
    print('startdate is xxx:',yesterday)
    print('enddate is:',todaystr)
    addtext = addtext + f'Startdate: {yesterday}<br>Enddate: {todaystr}'

    # for j,startdate in enumerate(startdates):
    # enddate=enddates[j]
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
                            print(f'cr is:{cr}')
                            dpt = cr[1].split()
                            print(f'dpt is:{dpt}')
                            mydate = datetime.strptime(dpt[0], '%m/%d/%Y')
                            mydate = mydate.date()
                            mytime = f'{dpt[1]} {dpt[2]}'
                            mytimedt = datetime.strptime(mytime, '%I:%M %p')
                            mytime = mytimedt.strftime('%H:%M')
                            print('mytime =', mytime) if printif == 1 else 1
                            print('cutoff =',cutoff) if printif == 1 else 1
                            if thiscon == confind and movetyp == typefind: conrecords.append(cr)

                        else:
                            print(f'Could not get the container or movetyp value for this record {i} of {numrec+1}')

                    #These are the records that will be put in database
                    for rec in conrecords:

                        thiscon = rec[2]
                        movetyp = rec[0]
                        clink = rec[3]
                        browser.get(clink)
                        time.sleep(2)

                        contentstr = '/html/body/table/tbody/tr[3]/td/table/tbody/tr/td[3]'
                        selectElem = browser.find_element_by_xpath(contentstr)
                        exitdt = selectElem.text
                        print(f'Exit Date-Time: {exitdt}')
                        dpt_exit = exitdt.split()
                        try:
                            exit_time = dpt_exit[1]
                        except:
                            exit_time = '00:00'
                        print(f'Exit time: {exit_time}')


                        conset = {}
                        con_data = browser.page_source
                        con_data = con_data.replace('</head>', '<style> table.center { margin-left: auto; margin-right: auto;}</style></head>')
                        con_data = con_data.replace('<table style="border: 1pt',
                                                    '<table class="center" style="border: 1pt')

                        print(con_data)
                        print(f'Here is gate ticket maker, now need to convert from {scac} to {scac2} and from {company} to {company2}')
                        con_data = con_data.replace(f'{scac}:', f'{scac2}:')
                        con_data = con_data.replace(company, company2)
                        print(con_data)
                        s['html'] = con_data
                        return s




            else:
                print(f'Logon failed with trys = {logontrys}')
                addtext = addtext + f'Logon failed with trys = {logontrys}'

            browser.quit()

    return addtext, newadd, newinterchange, errors



for s in sh:
    godate = s['Date']
    container = s['Container']
    print(f'Getting container records for {container} on the date {godate}')
    s = gatescraper(printif, s)


print('Have completed all the tickets, now print and upload the interchange into the new scac2 database')

for ix, s in enumerate(sh):
    htmldat = s['html']
    con = s['Container']
    typef = s['Type']
    #print(f'outpath is: {outpath}')
    #print(f'viewfile is {viewfile}')
    #pfile = outpath + viewfile
    pfile = f'/home/mark/{con}_{typef}.pdf'
    hfile = f'/home/mark/{con}_{typef}.html'
    print(f'pfile is {pfile}')
    pdfkit.from_string(htmldat, pfile)
    with open(hfile, 'w') as f:
        f.write(htmldat)

if nt == 'remote': tunnel.stop()
quit()
