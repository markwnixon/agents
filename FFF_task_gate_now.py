import os
import sys
from bs4 import BeautifulSoup as soup
import time
from datetime import datetime, timedelta
from pyvirtualdisplay import Display
from selenium import webdriver
import pdfkit
from PyPDF2 import PdfFileReader, PdfFileWriter, PdfFileMerger
from PyPDF2.pdf import PageObject
from utils import hasinput

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


linkto = 'newclass8'
scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running FFF_task_gate_now for {scac} in tunnel mode: {nt}')
    os.environ['SCAC'] = scac
    os.environ['PURPOSE'] = 'script'
    os.environ['MACHINE'] = 'ubuntu1700'
    os.environ['TUNNEL'] = nt
    if linkto == 'oldclass8':
        os.environ['LINKTO'] = 'oldclass8'
        from remote_db_connect import tunnel, db
        from models import Orders, Interchange, Invoices
    elif linkto == 'newclass8':
        os.environ['LINKTO'] = 'newclass8'
        from remote_db_connect import db
        if nt == 'remote': from remote_db_connect import tunnel
        from models8 import Interchange, Orders, Drivers, Pins
        from CCC_system_setup import websites, usernames, passwords, addpath3, addpath
        from email_reports import emailtxt
        from cronfuncs import conmatch
else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO so getting inputs for CCC-system_setup')
    from CCC_system_setup import addpath3, websites, usernames, passwords, lt, scac, nt, addpath

    if linkto == 'oldclass8':
        from models import Interchange, Orders
    elif linkto == 'newclass8':
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
def blendticks(gfile1,gfile2,outfile):

    reader1 = PdfFileReader(open(gfile1, 'rb'))
    p1 = reader1.getPage(0)

    reader2 = PdfFileReader(open(gfile2, 'rb'))
    p2 = reader2.getPage(0)

    g3 = '/home/mark/flask/crontasks/incoming/blank.pdf'
    reader3 = PdfFileReader(open(g3, 'rb'))
    p3 = reader3.getPage(0)
    #p2.cropBox.lowerLeft = (50,400)
    #p2.cropBox.upperRight = (600,700)
    #translate first page
    p3.mergeTranslatedPage(p1, 0, -100, expand=False)


    #offset_x = p2.mediaBox[2]
    offset_x = 0
    #offset_y = -280
    offset_y = -325

    # add second page to first one
    p3.mergeTranslatedPage(p2, offset_x, offset_y, expand=False)
    p3.cropBox.lowerLeft = (50,250)
    p3.cropBox.upperRight = (550,800)

    output = PdfFileWriter()
    output.addPage(p3)

    with open(outfile, "wb") as out_f:
        output.write(out_f)

def make_blended(odat,ingate,outgate):
    # Make blended tickets for this matched container
    con = odat.Container
    jo = odat.Jo
    gate = odat.Gate
    pdf1 = ingate.Source
    pdf2 = outgate.Source
    test = 0
    if con in pdf1 and con in pdf2 and 'OUT' in pdf1 and ('IN' in pdf2 or 'Source' in pdf2): test = 1
    print(f'For order {jo} we have container {con} and pdf files {pdf1} and {pdf2} and test is {test}')
    if test == 1:
        blendfile = f'{con}_Blended.pdf'
        scp_path = f'{websites["ssh_data"] + "vGate/"}'
        scpfile = scp_path + blendfile
        tempfile = addpath3(f'{scac}/{blendfile}')
        tempfile1 = addpath3(f'{scac}/{pdf1}')
        tempfile2 = addpath3(f'{scac}/{pdf2}')

        scpcom = f'scp {scpfile} {tempfile}'
        scpcom1 = f'scp {scp_path}{pdf1} {tempfile1}'
        scpcom2 = f'scp {scp_path}{pdf2} {tempfile2}'
        newdoc = f'static/{scac}/data/vGate/{con}_Blended.pdf'
        print(f'The blended file is: {blendfile}')

        try:
            os.system(scpcom)
        except:
            print('File does not exist')
        try:
            os.system(scpcom1)
            os.system(scpcom2)
        except:
            print('Files do not exist')

        if os.path.isfile(tempfile):
            print(f'{blendfile} exists already')
            odat.Gate = f'{con}_Blended.pdf'
            db.session.commit()
            os.remove(tempfile1)
            os.remove(tempfile2)
            os.remove(tempfile)
        elif os.path.isfile(tempfile1) and os.path.isfile(tempfile2):
            # g1 = f'static/{scac}/data/vGate/{pdf1}'
            # g2 = f'static/{scac}/data/vGate/{pdf2}'
            blendticks(tempfile1, tempfile2, tempfile)
            odat.Gate = f'{con}_Blended.pdf'
            db.session.commit()
            if os.path.isfile(tempfile):
                copyline = f'scp {tempfile} {websites["ssh_data"] + "vGate"}'
                print('copyline=', copyline)
                os.system(copyline)
                os.remove(tempfile1)
                os.remove(tempfile2)
                os.remove(tempfile)


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
            okat = Orders.query.filter(Orders.Booking == release).order_by(Orders.id.desc()).first()
            driver = get_driver(movetyp, release)
            if okat is not None:
                ikat.Jo = okat.Jo
                ikat.Status = 'Out'
                ikat.Company = okat.Shipper
                ikat.Driver = driver
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
            okat = Orders.query.filter(Orders.Container==thiscon).first()
            driver = get_driver(movetyp, con)
            if okat is not None:
                ikat.Jo = okat.Jo
                ikat.Company = okat.Shipper
                ikat.Driver = driver
                okat.Chassis = ikat.Chassis
                okat.Date2 = ikat.Date
                okat.BOL = ikat.Release
                okat.Hstat = 2
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

def gatescraper(printif, dayback):

    newadd = 0
    newinterchange = []
    errors = 0
    username = usernames['gate']
    password = passwords['gate']
    print('username,password=',username,password)
    addtext = ''

    outpath = addpath3('interchange/')
    print('Entering Firefox') if printif == 1 else 1
    yesterday = datetime.strftime(datetime.now() - timedelta(dayback), '%m/%d/%Y')
    todaystr = datetime.strftime(datetime.now() - timedelta(dayback), '%m/%d/%Y')
    today = datetime.today()
    cutoff = datetime.now() - timedelta(30)
    cutoff = cutoff.date()
    #todaystr = datetime.today().strftime('%m/%d/%Y')
    startdate = yesterday
    enddate = todaystr
    consets = []
    print('startdate is:',yesterday)
    print('enddate is:',todaystr)
    addtext = addtext + f'Startdate: {yesterday}<br>Enddate: {todaystr}'

    # for j,startdate in enumerate(startdates):
    # enddate=enddates[j]
    with Display():
    #display = Display(visible=0, size=(800, 1080))
    #display.start()
        logontrys = 1
        logonyes = 0
        url1 = websites['gate']
        browser = webdriver.Firefox()

        while logontrys<4 and logonyes == 0:

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


            try:
                #containers = browser.find_elements_by_xpath('//a[contains(@href,"ticket")]')
                conrecords = []
                for i in range(1,numrec+1):
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
                        print(cr) if printif == 1 else 1
                        dpt = cr[1].split()
                        print('dpt=', dpt) if printif == 1 else 1
                        mydate = datetime.strptime(dpt[0], '%m/%d/%Y')
                        mydate = mydate.date()
                        mytime = f'{dpt[1]} {dpt[2]}'
                        mytimedt = datetime.strptime(mytime, '%I:%M %p')
                        mytime = mytimedt.strftime('%H:%M')
                        print('mytime =', mytime) if printif == 1 else 1
                        print('cutoff =',cutoff) if printif == 1 else 1
                        idat = Interchange.query.filter( (Interchange.Container == thiscon) & (Interchange.Type == movetyp) & (Interchange.Date > cutoff) ).first()
                        if idat is None:

                            contype = f'{cr[4]} {cr[5]} {cr[6]}'
                            if linkto == 'newclass8':
                                input = Interchange(Container=thiscon, TruckNumber='NAY', Driver='NAY', Chassis=cr[8],
                                                    Date=mydate, Release=cr[11], GrossWt='NAY', Seals='NAY', ConType=contype, CargoWt='NAY',
                                                    Time=mytime, Status='AAAAAA', Source='NAY', Path=cr[7], Type=movetyp, Jo='NAY', Company='NAY', Other=None)
                            if linkto == 'oldclass8':
                                input = Interchange(Container=thiscon, TruckNumber='NAY', Driver='NAY', Chassis=cr[8],
                                                    Date=mydate, Release=cr[11], GrossWt='NAY', Seals='NAY', ConType=contype, CargoWt='NAY',
                                                    Time=mytime, Status='AAAAAA', Original='NAY', Path=cr[7], Type=movetyp, Jo='NAY', Company='NAY', Other=None)
                            db.session.add(input)
                            db.session.commit()
                            newadd = 1
                            print(f'***Adding {thiscon} {movetyp} on {mydate} at {mytime} to database')
                            addtext = addtext + f'<br>***Adding {thiscon} {movetyp} on {mydate} at {mytime} to database'
                            conrecords.append(cr)
                        else:
                            print(f'Record for {thiscon} {movetyp} on {mydate} at {mytime} already in database')
                            addtext = addtext + f'<br>Record for {thiscon} {movetyp} on {mydate} at {mytime} already in database'
                    else:
                        print(f'Could not get the container or movetyp value for this record {i} of {numrec+1}')

                #These are the records that will be put in database
                for rec in conrecords:

                    thiscon = rec[2]
                    movetyp = rec[0]
                    clink = rec[3]
                    browser.get(clink)
                    time.sleep(2)
                    conset = {}
                    con_data = browser.page_source
                    con_data = con_data.replace('</head>', '<style> table.center { margin-left: auto; margin-right: auto;}</style></head>')
                    con_data = con_data.replace('<table style="border: 1pt',
                                                '<table class="center" style="border: 1pt')
                    testdata = con_data.splitlines()
                    #page_soup = soup(con_data, 'html.parser')
                    keys = ['TRUCK NUMBER:', 'CHASSIS:', 'GROSS WT:', 'CARGO WT:', 'SEALS:', 'CONTAINER:', 'SIZE/TYPE:']
                    labels = ['TruckNumber', 'Chassis', 'GrossWt', 'CargoWt', 'Seals', 'Container', 'Size']

                    for line in testdata:
                        for jx,key in enumerate(keys):
                            if key in line:
                                #print(f'key found {key} in line: {line}')
                                res = line.split(key,1)
                                value = res[1]
                                value = value.replace('</td>','')
                                value = value.strip()
                                #print(value)
                                newkey = labels[jx]
                                conset.update({newkey: value})

                    idat = Interchange.query.filter((Interchange.Container == thiscon) & (Interchange.Type == movetyp) & (Interchange.Date > cutoff)).first()

                    if idat is not None:

                        type = movetyp.upper()
                        type = type.replace(' ', '_')
                        viewfile = thiscon + '_' + type + '.pdf'

                        idat.Chassis = conset.get("Chassis")
                        idat.TruckNumber = conset.get("TruckNumber")
                        idat.GrossWt = conset.get("GrossWt")
                        idat.CargoWt = conset.get("CargoWt")
                        idat.Seals = conset.get("Seals")
                        if linkto == 'newclass8':
                            idat.Source = viewfile
                        if linkto == 'oldclass8':
                            idat.Original = viewfile

                        newinterchange.append(idat.id)

                        db.session.commit()

                        #print(f'con_data:{con_data}')
                        pdfkit.from_string(con_data, outpath+viewfile)
                        newfile = outpath + viewfile

                        #newfile = moveticks(newfile)
                        if linkto == 'oldclass8':
                            copyline = f'scp {newfile} {websites["ssh_data"]+"vinterchange"}'
                        elif linkto == 'newclass8':
                            copyline = f'scp {newfile} {websites["ssh_data"]+"vGate"}'

                        print('copyline=',copyline)
                        os.system(copyline)
                        #os.remove(newfile)
                        print('Now updating records')
                        retval = update_records(thiscon, idat.id)
                        print(f'The return value is {retval}')
            except:
                addtext = addtext + f'\n\nFailure with something in container match system'
                errors += 1
                return addtext, newadd, newinterchange, errors

        else:
            print(f'Logon failed with trys = {logontrys}')
            addtext = addtext + f'Logon failed with trys = {logontrys}'
        browser.quit()
    return addtext, newadd, newinterchange, errors


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
title = f'{scac} Cron run for Gate Now at {runat} with for daysback: {daybackvec}'
print(f'{scac} Cron run for Gate Now at {runat} with for daysback: {daybackvec}')
for ix in daybackvec:
    print('Running this far back:',ix)
    textblock = f'{textblock} <br> Running this far back: {ix}'
    addtext, newadd, newinterchange, errors = gatescraper(printif, ix)
    try:
        #if newadd: addtext = conmatch(addtext, newinterchange)
        textblock = f'{textblock} <br><br> {addtext}\n'
        if newadd:
            emailtxt(title, textblock)
        elif errors > 0:
            emailtxt(title, textblock)
        else:
            textblock = textblock + '<br> No new add and no errors'
            #emailtxt(title, textblock)

    except:
        textblock = f'{textblock} <br><br> {addtext}\n'
        finat = datetime.now()
        title = f'{scac} Cron run for Gate Now at {runat} failed at {finat}'
        emailtxt(title, f'Failed in conmatch on day back {ix}<br><br>Textblock:{textblock}')

if nt == 'remote': tunnel.stop()
