import os
import shutil
import sys
import socket
from utils import getpaths
from bs4 import BeautifulSoup as soup
import time
from datetime import datetime, timedelta

import pdfkit
from PyPDF2 import PdfReader, PdfWriter, Transformation
#from PyPDF2 import PageObject
from utils import hasinput

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    container = sys.argv[2]
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


def html_scraper(thiscon, movetyp, htmldat):

    if hasinput(thiscon) and hasinput(movetyp):

        cutoff = datetime.now() - timedelta(45)
        cutoff = cutoff.date()
        conset = {}
        outpath = addpath3('interchange/')

        testdata = htmldat.splitlines()
        # page_soup = soup(con_data, 'html.parser')
        keys = ['TRUCK NUMBER:', 'CHASSIS:', 'GROSS WT:', 'CARGO WT:', 'SEALS:', 'CONTAINER:', 'SIZE/TYPE:', 'In Time:', 'RELEASE']
        labels = ['TruckNumber', 'Chassis', 'GrossWt', 'CargoWt', 'Seals', 'Container', 'Size', 'Dtstring', 'Release']
        onlyonce = False
        for line in testdata:
            for jx, key in enumerate(keys):
                if key in line:
                    if key == 'SIZE/TYPE:' and onlyonce:
                        print('Already did size/type')
                    else:
                        res = line.split(key, 1)
                        value = res[1]
                        value = value.replace('</td>', '')
                        value = value.strip()
                        print(value)
                        newkey = labels[jx]
                        print(f'newkey is {newkey} with a value {value}')
                        conset.update({newkey: value})
                        if key == 'SIZE/TYPE:':
                            onlyonce = True


        print(conset)
        datestr = conset['Dtstring']
        dt = datetime.strptime(datestr, '%Y-%m-%d %H:%M')
        ticket_date = dt.date()
        ticket_time = dt.time()
        print(f'ticket date is {ticket_date}')

        contype = conset['Size']
        contype = contype.replace('40','40\'')
        contype = contype.replace('20', '20\'')
        contype = contype.replace('96', '9\'6"')
        contype = contype.replace('86', '8\'6"')

        pathfile = f'/home/mark/{thiscon}_{movetyp}.pdf'
        type = movetyp.upper()
        type = type.replace(' ', '_')
        viewfile = thiscon + '_' + type + '.pdf'
        newfile = outpath + viewfile
        #Place the pdf file into the local code
        print(newfile)
        shutil.copy(pathfile, newfile)

        idat = Interchange.query.filter( (Interchange.Container == thiscon) & (Interchange.Type == movetyp) & (Interchange.Date > cutoff) ).first()
        if idat is None:

            input = Interchange(Container=thiscon, TruckNumber=conset['TruckNumber'], Driver='NAY', Chassis=conset['Chassis'],
                                Date=ticket_date, Release=conset['Release'], GrossWt=conset['GrossWt'], Seals=conset['Seals'], ConType=contype, CargoWt=conset['CargoWt'],
                                Time=ticket_time, Status='AAAAAA', Source=viewfile, Path='NAY', Type=movetyp, Jo='NAY', Company='NAY', Other=None,
                                TimeExit=None, PortHours=None)

            db.session.add(input)
            db.session.commit()
            newadd = 1
            print(f'***Adding {thiscon} {movetyp} on {ticket_date} at {ticket_time} to database')
            copyline = f'scp {newfile} {websites["ssh_data"] + "vGate"}'
            print('uploading the gate ticket copyline=', copyline)
            os.system(copyline)

        #Next update the order if it exists
        idat = Interchange.query.filter((Interchange.Container == thiscon) & (Interchange.Type == movetyp) & (Interchange.Date > cutoff)).first()
        if idat is not None:
            id1 = idat.id
            update_records(thiscon, id1)
    return



########################################################################3
print(f'Running FFF_Gate_Shuttle_Update.py to create or update job associated with container {container} and scac {scac}')
# First get the html file stored for the container

def matching_html_files(directory, name_part):
    return [
        f for f in os.listdir(directory)
        if name_part in f and f.endswith(".html")
    ]


root_dir = '/home/mark'
files = matching_html_files(root_dir, container)
print(files)

for file in files:
    #Extract the type from the file name
    filepath = f'/home/mark/{file}'
    name, ext = os.path.splitext(file)
    containeri, typef = name.split('_')
    print(f'Found {file} with container {containeri} and typef {typef}')
    with open(filepath, "r", errors="ignore") as f:
        htmldat = f.read()
        #print(htmldat)
        html_scraper(container, typef, htmldat)


quit()
if nt == 'remote': tunnel.stop()
