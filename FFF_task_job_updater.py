from datetime import datetime, timedelta
import os
import sys
from PyPDF2 import PdfReader, PdfWriter, Transformation
import socket
from utils import getpaths

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    scac = 'fela'

scac = scac.upper()
nt = 'remote'

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running FFF_task_gate_now for {scac} in tunnel mode: {nt}')

    host_name = socket.gethostname()
    print("Host Name:", host_name)
    dropbox_path = getpaths(host_name, 'dropbox')
    sys_path = getpaths(host_name, 'system')
    sys.path.append(sys_path) #So we can import CCC_system_setup from full path

    os.environ['SCAC'] = scac
    os.environ['PURPOSE'] = 'script'
    os.environ['MACHINE'] = host_name
    os.environ['TUNNEL'] = nt

    from remote_db_connect import tunnel, db
    from models8 import Interchange, Orders, Drivers, Pins, Orders, OverSeas, People, Drops
    from CCC_system_setup import websites, usernames, passwords, addpath3, addpath, addpaths
    from email_reports import emailtxt
    from cronfuncs import conmatch
else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

from utils import hasinput
from cronfuncs import tunneltest, Order_Container_Update

success = tunneltest()

printif = 0

runat = datetime.now()
today = runat.date()
tomorrow = runat + timedelta(1)
lookback = runat - timedelta(30)
lookback_ocean = runat - timedelta(20)
lbdate = lookback.date()
lbdate_ocean = lookback_ocean.date()
print(' ')
print('________________________________________________________')
print(f'This sequence run at {runat} with look back to {lbdate}')
print('________________________________________________________')
print(' ')

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
    #p3.mergeTranslatedPage(p1, 0, -100, expand=False)
    p1.add_transformation(Transformation().translate(tx=0, ty=-80))
    p3.merge_page(p1)


    #offset_x = p2.mediaBox[2]
    offset_x = 0
    #offset_y = -280
    offset_y = -325

    # add second page to first one
    #p3.mergeTranslatedPage(p2, offset_x, offset_y, expand=False)
    #p3.cropBox.lowerLeft = (50,250)
    #p3.cropBox.upperRight = (550,800)
    p2.add_transformation(Transformation().translate(tx=offset_x, ty=offset_y))
    p3.merge_page(p2)
    #p3.cropbox.lower_left = (50,250)
    p3.cropbox.lower_left = (50, 150)
    p3.cropbox.upper_right = (550,800)

    output = PdfFileWriter()
    output.addPage(p3)

    with open(outfile, "wb") as out_f:
        output.write(out_f)

#Make sure all the booking and container numbers for orders have upper case:
#These correction made only once, using Release...set to 1 after corrections
jdata = Orders.query.filter( (~Orders.Status.endswith('3')) & (Orders.Date > lbdate) & (Orders.Release == 0) ).all()
for jdat in jdata:
    bk = jdat.Booking
    if hasinput(bk):
        bk = bk.upper()
        bk = bk.strip()
    else:
        bk = ''
    con = jdat.Container
    if hasinput(con):
        con = con.upper()
        con = con.strip()
    else:
        con = ''
    jdat.Booking = bk
    jdat.Container = con
    jdat.Release = 1
    db.session.commit()

# Make sure there is a delivery date
odata = Orders.query.filter( (Orders.Hstat > 0) & (Orders.Date > lbdate)).all()
for odat in odata:
    #Double check a delivery date has been set
    dd = odat.Date3
    dout = odat.Date
    if dd is None:
        if dout is not None:
            print(f'Updating delivery date for {odat.Jo}')
            odat.Date3 = dout
        db.session.commit()
    #Make sure the Istat is zero if it is set to None
    istat = odat.Istat
    if istat is None:
        odat.Istat = 0
        db.session.commit()

# Update all the containers that are not already returned
odata = Orders.query.filter( (Orders.Hstat < 2) & (Orders.Date > lbdate)).all()
for odat in odata:
    sid = odat.id
    Order_Container_Update(sid)

sids = []
# Find any unassigned interchange tickets and attempt to locate the jobs
idata = Interchange.query.filter( (Interchange.Jo == 'NAY') & (Interchange.Date > lbdate)).all()
for idat in idata:
    odat = Orders.query.filter( (Orders.Booking == idat.Release) & (Orders.Date > lbdate)).first()
    if odat is None:
        odat = Orders.query.filter( (Orders.Container == idat.Container) & (Orders.Date > lbdate) ).first()
    if odat is not None:
        sid = odat.id
        if sid not in sids: sids.append(sid)
        print(odat.Container,idat.Container)

idata = Interchange.query.filter( (Interchange.Jo == '') & (Interchange.Date > lbdate)).all()
for idat in idata:
    odat = Orders.query.filter( (Orders.Booking == idat.Release) & (Orders.Date > lbdate)).first()
    if odat is None:
        odat = Orders.query.filter( (Orders.Container == idat.Container) & (Orders.Date > lbdate) ).first()
    if odat is not None:
        sid = odat.id
        if sid not in sids: sids.append(sid)
        print(odat.Container,idat.Container)

print(sids)
for sid in sids:
    Order_Container_Update(sid)

#Make blended tickets for jobs where containers are matched and not yet emailed over last 30 days
odata = Orders.query.filter( (Orders.Hstat > 1) & (Orders.Istat < 3) & (Orders.Date > lbdate)).all()
for odat in odata:
    con = odat.Container
    jo = odat.Jo
    gate = odat.Gate
    if not hasinput(gate):
        idata = Interchange.query.filter(Interchange.Jo == jo).all()
        if len(idata) == 2:
            idat1 = idata[0]
            idat2 = idata[1]
            if 'IN' in idat1.Source:
                #Then switch to the out is first:
                idat1 = idata[1]
                idat2 = idata[0]
            pdf1 = idat1.Source
            pdf2 = idat2.Source
            test = 0
            if con in pdf1 and con in pdf2 and 'OUT' in pdf1 and ('IN' in pdf2 or 'Source' in pdf2):
                test = 1
            print(f'For order {jo} we have container {con} and pdf files {pdf1} and {pdf2} and test is {test}')
            if test == 1:
                blendfile = f'{con}_Blended.pdf'
                scp_path = f'{websites["ssh_data"]+"vGate/"}'
                scpfile = scp_path+blendfile
                tempfile = addpath3(f'{scac}/{blendfile}')
                tempfile1 = addpath3(f'{scac}/{pdf1}')
                tempfile2 = addpath3(f'{scac}/{pdf2}')

                scpcom = f'scp {scpfile} {tempfile}'
                scpcom1 = f'scp {scp_path}{pdf1} {tempfile1}'
                scpcom2 = f'scp {scp_path}{pdf2} {tempfile2}'
                newdoc = f'static/{scac}/data/vGate/{con}_Blended.pdf'
                print(blendfile)
                print(scp_path)
                print(scpfile)
                print(tempfile)
                print(scpcom)
                print(scpcom1)
                print(scpcom2)
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
                    #g1 = f'static/{scac}/data/vGate/{pdf1}'
                    #g2 = f'static/{scac}/data/vGate/{pdf2}'
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




#Make sure there are no doubled up Global Jobs
jdata = Orders.query.filter( (Orders.Shipper == 'Global Business Link') & (Orders.Date > lbdate)).all()
for jdat in jdata:

    bk = jdat.Booking
    con = jdat.Container

    # Do not want to include container matches if they are TBD
    if con == 'TBD' or len(con) < 9:
        con = 'XXX'
    if len(bk) < 6:
        bk = 'YYY'
    #rint(f'Global Job {jdat.Booking} and {jdat.Container} with Status {jdat.Status}')


    #Now see if there are trucking jobs of other companies that got mixed up with Global:
    tdat = Orders.query.filter( (Orders.id != jdat.id) & (Orders.Date > lbdate) & ((Orders.Booking == bk) | (Orders.Container == con)) ).first()
    if tdat is not None:
        # Have a duplicate with order booking or container: delete the Global Job
        killid = jdat.id
        print(f'Have Global duplicate with Order {bk} | {con}')
        Orders.query.filter(Orders.id == killid).delete()
        db.session.commit()

        # Now refranchise the Interchange Tickets just in Case they have Global Label:
        idata = Interchange.query.filter(((Interchange.Container == con) | (Interchange.Release == bk)) & (Interchange.Date > lbdate)).all()
        for idat in idata:
            idat.Jo = tdat.Jo
            idat.Company = tdat.Shipper
            db.session.commit()

# Match up the containers that can be matched up IN to OUT matching
idata = Interchange.query.filter( (Interchange.Type.contains('Out') & (Interchange.Date > lbdate)) ).all()
for idat in idata:
    type = idat.Type
    con = idat.Container
    if 'Out' in type:
        #We have an out container, need to match to the In container.
        imat = Interchange.query.filter( (Interchange.Container == con)  & (Interchange.Type.contains('In')) & (Interchange.Date > lbdate) ).first()
        if imat is not None:
            imat.Status = 'IO'
            idat.Status = 'IO'
        else:
            idat.Status = 'BBBBBB'
        db.session.commit()

# find containers in that did not go out...
idata = Interchange.query.filter( (Interchange.Type.contains('Out') & (Interchange.Date > lbdate)) ).all()
for idat in idata:
    type = idat.Type
    con = idat.Container
    if 'In' in type:
        #We have an out container, need to match to the In container.
        imat = Interchange.query.filter( (Interchange.Container == con) & (Interchange.Type.contains('Out')) & (Interchange.Date > lbdate) ).first()
        if imat is None:
            idat.Status = 'Unmatched'
            db.session.commit()

# Change the scheduled day for jobs that have not been pulled, but have dates past today
odata = Orders.query.filter((Orders.Hstat < 1) & (Orders.Date > lbdate)).all()
for odat in odata:
    date1 = odat.Date
    date2 = odat.Date2
    date3 = odat.Date3
    if date1 < today:
        odat.Date = today
    if date2 < today:
        odat.Date2 = tomorrow
    if date3 is None:
        odat.Date3 = today
    else:
        if date3 < today:
            print(f'Update delivery date for JO {odat.Jo} to {date3}')
            odat.Date3 = today
db.session.commit()


if nt == 'remote': tunnel.stop()