import datetime
from CCC_system_setup import lt
from remote_db_connect import db
if lt == 'oldclass8':
    from models import JO, Drops, Interchange, Orders
elif lt == 'newclass8':
    from models8 import JO, Drops, Interchange, Orders

from datetime import timedelta
from utils import hasinput

today = datetime.date.today()

def tunneltest():
    # Hold Tunnel Open to Ensure Links
    success = 0
    trys = 0
    while success == 0 and trys < 20:
        try:
            test = JO.query.filter(JO.id > 1).first()
            print(f'Successfully opened tunnel to JO id {test.id}')
            success = 1
        except:
            print(f'Could not open tunnel on try {trys+1}')
            trys = trys + 1
    return success

def nodollar(infloat):
    outstr = "%0.2f" % infloat
    return outstr


def dollar(infloat):
    outstr = '$'+"%0.2f" % infloat
    return outstr


def avg(in1, in2):
    out = (in1+in2)/2
    return out


def stat_update(status, newval, i):
    a = list(status)
    a[i] = newval
    b = ''.join(a)
    return b


def nonone(input):
    if input is not None:
        output = int(input)
    else:
        output = 0
    return output


def d2s(instr):
    try:
        instr = instr.replace('$', '').replace(',', '')
    except:
        instr = str(instr)
    try:
        infloat = float(instr)
        outstr = "%0.2f" % infloat
    except:
        outstr = instr
    return outstr

def d1s(instr):
    try:
        instr = instr.replace('$', '').replace(',', '')
    except:
        instr = str(instr)
    try:
        infloat = float(instr)
        outstr = "%0.1f" % infloat
    except:
        outstr = instr
    return outstr

def newjo(jtype,sdate):
    dt = datetime.datetime.strptime(sdate, '%Y-%m-%d')
    year= str(dt.year)
    day=str(dt.day)
    month=str(dt.month)
    lv=JO.query.get(1)
    nextid=lv.nextid
    eval=str(nextid%100).zfill(2)
    day2="{0:0=2d}".format(int(day))
    if month=='10':
        month='X'
    if month=='11':
        month='Y'
    if month=='12':
        month='Z'

    nextjo = jtype+month+day2+year[3]+eval
    input2 = JO(jo=nextjo, nextid=0, date=sdate, status=1)
    db.session.add(input2)
    lv.nextid=nextid+1
    db.session.commit()
    return nextjo

def dropupdate(dropblock):
    droplist=dropblock.splitlines()
    avec=[' ']*5
    for j,drop in enumerate(droplist):
        if j<5:
            avec[j]=drop
    entity=avec[0]
    addr1=avec[1]
    edat=Drops.query.filter((Drops.Entity==entity) & (Drops.Addr1==addr1)).first()
    if edat is None:
        input = Drops(Entity=avec[0],Addr1=avec[1],Addr2=avec[2],Phone=avec[3],Email=avec[4])
        db.session.add(input)
        db.session.commit()
    return entity

def seektaken(container,dstart):
    ocheck = Orders.query.filter((Orders.Container==container) & (Orders.Date>dstart) ).first()
    if ocheck is not None: return 1
    else: return 0

def checkon(con,bk):
    if not hasinput(con): con = ''
    if not hasinput(bk): bk = ''
    if con == 'TBD' or len(con) < 9:
        retcon = 'XXX'
    else:
        retcon = con
    if len(bk) < 6:
        retbk = 'YYY'
    else:
        retbk = bk
    return retcon, retbk

def conmatch(addtext, newinterchange):
    runat = datetime.datetime.now()
    today = runat.date()
    lookback = runat - timedelta(45)
    lbdate = lookback.date()

    for thisid in newinterchange:
        idat = Interchange.query.get(thisid)
        print(idat.id, idat.Container, idat.Type)
        con = idat.Container
        typ = idat.Type
        rel = idat.Release
        con, rel = checkon(con,rel)

        if typ == 'Load In':
            # This must be an export and need to make sure the order has container number
            odat = Orders.query.filter((Orders.Container == con) & (Orders.Date > lbdate)).first()
            if odat is None:
                odat = Orders.query.filter((Orders.Booking == rel) & (Orders.Date > lbdate)).first()
            if odat is None:
                addtext = f'{addtext} <br> Could not find an order to match container {con} {typ}'
            else:
                # Shoud be an export
                idat.Status = 'BBBBBB'
                idat.Company = odat.Shipper
                idat.Jo = odat.Jo
                odat.Date2 = idat.Date
                odat.Type = idat.ConType
                odat.Chassis = idat.Chassis
                odat.Hstat = 2

            #Try to find and match the empty out
            imat = Interchange.query.filter((Interchange.Container == con) & (Interchange.Type.contains('Out')) & (Interchange.Date > lbdate)).first()
            if imat is not None:
                imat.Status = 'IO'
                idat.Status = 'IO'
                if odat is not None:
                    imat.Company = odat.Shipper
                    imat.Jo = odat.Jo
            else:
                addtext = f'{addtext} <br> Could not find an outbound interchange ticket to match container {con} {typ}'
                # Since there is no outbound we need to set the date and container for the job by the inbound if there is a job
                if odat is not None:
                    odat.Date = idat.Date
                    odat.Container = idat.Container

            db.session.commit()

        if typ == 'Empty In':
        # This must be an import and need to make sure the order has container number
            odat = Orders.query.filter((Orders.Container == con) & (Orders.Date > lbdate)).first()
            if odat is None:
                odat = Orders.query.filter((Orders.Booking == rel) & (Orders.Date > lbdate)).first()
            if odat is None:
                textblock = f'{textblock} <br> Could not find an order to match container {con} {typ}'
            else:
                #Shoud be an import
                idat.Status = 'BBBBBB'
                idat.Company = odat.Shipper
                idat.Jo = odat.Jo
                odat.Date2 = idat.Date
                odat.Type = idat.ConType
                odat.Chassis = idat.Chassis
                odat.Hstat = 2

            # Try to find and match the load out
            imat = Interchange.query.filter((Interchange.Container == con) & (Interchange.Type.contains('Out')) & (Interchange.Date > lbdate)).first()
            if imat is not None:
                imat.Status = 'IO'
                idat.Status = 'IO'
                if odat is not None:
                    imat.Company = odat.Shipper
                    imat.Jo = odat.Jo
            else:
                addtext = f'{addtext} <br> Could not find an outbound interchange ticket to match container {con} {typ}'
                # Since there is no outbound we need to set the date and container for the job by the inbound if there is a job
                if odat is not None:
                    odat.Date = idat.Date
                    odat.Container = idat.Container

            db.session.commit()

        if typ == 'Load Out' or typ == 'Empty Out':
            # This must be an export and need to make sure the order has container number
            odat = Orders.query.filter((Orders.Container == con) & (Orders.Date > lbdate)).first()
            if odat is None:
                odat = Orders.query.filter((Orders.Booking == rel) & (Orders.Date > lbdate)).first()
            if odat is None:
                addtext = f'{addtext} <br> Could not find an order to match container {con} {typ}'
            else:
                # Shoud be an export
                idat.Status = 'BBBBBB'
                idat.Company = odat.Shipper
                idat.Jo = odat.Jo
                odat.Date = idat.Date
                odat.Type = idat.ConType
                odat.Chassis = idat.Chassis
                odat.Container = idat.Container
                hstat = odat.Hstat
                if hstat is None: hstat = 0
                if hstat < 2: odat.Hstat = 1

            # Try to find and match the in ticket just in case the out ticket put in later
            imat = Interchange.query.filter((Interchange.Container == con) & (Interchange.Type.contains('In')) & (Interchange.Date > lbdate)).first()
            if imat is not None:
                imat.Status = 'IO'
                idat.Status = 'IO'
                if odat is not None:
                    imat.Company = odat.Shipper
                    imat.Jo = odat.Jo
            else:
                addtext = f'{addtext} <br> Verified that the inbound interchange ticket to match container {con} {typ} not yet in system'

            db.session.commit()

    return addtext

def Order_Container_Update(oder):
    odat = Orders.query.get(oder)
    bk = odat.Booking
    bol = odat.BOL
    container = odat.Container
    try:
        ht = odat.HaulType
    except:
        if bk == bol: ht = 'Import'
        else: ht = 'Export'

    start_date = odat.Date - timedelta(30)
    end_date = odat.Date + timedelta(30)
    pulled = False
    returned = False
    jimport = False
    jexport = False

    if 'Import' in ht and hasinput(container):
        jimport = True
        idata = Interchange.query.filter( (Interchange.Date > start_date) & (Interchange.Date < end_date) & (Interchange.Container == container) ).all()
        for jx,idat in enumerate(idata):
            type =  idat.Type
            if 'Out' in type:
                ao = idat
                pulled = True
            if 'In' in type:
                ai = idat
                returned = True
    elif 'Export' in ht and hasinput(bk):
        jexport = True
        idata = Interchange.query.filter((Interchange.Date > start_date) & (Interchange.Date < end_date) & (Interchange.Release == bk)).all()
        for jx,idat in enumerate(idata):
            type =  idat.Type
            if 'Out' in type:
                ao = idat
                pulled = True
                bkout = idat.Release
                # Container may be returned under different booking
                pulled_container = idat.Container
                rdat = Interchange.query.filter( (Interchange.Date > start_date) & (Interchange.Date < end_date) & (Interchange.Container == pulled_container) & ( Interchange.Type.contains('In')) ).first()
                if rdat is not None:
                    returned = True
                    ai = rdat

        if not pulled and not returned:
            #Check to see if missing the IN ticket and need to match the out by booking
            rdat = Interchange.query.filter((Interchange.Date > start_date) & (Interchange.Date < end_date) & (Interchange.Release == bk) & (Interchange.Type.contains('In'))).first()
            if rdat is not None:
                ai = rdat
                returned = True


    print(f'For sid {oder} we have container {container} and pulled is {pulled} and returned is {returned}')
    if pulled and not returned:
        odat.Hstat = 1
        ao.Company = odat.Shipper
        ao.Jo = odat.Jo
        odat.Date = ao.Date
        if odat.Istat == -1: odat.Istat = 0
        if jexport:
            odat.Container = ao.Container
        odat.Chassis = ao.Chassis
        odat.Type = ao.ConType
        db.session.commit()
    if pulled and returned:
        if not hasinput(ao.Company): ao.Company = odat.Shipper
        if not hasinput(ao.Jo): ao.Jo = odat.Jo
        if not hasinput(container): odat.Container = ai.Container
        if odat.Istat == -1: odat.Istat = 0
        ai.Company = odat.Shipper
        ai.Jo = odat.Jo
        odat.Hstat = 2
        odat.Date = ao.Date
        odat.Date2 = ai.Date
        if not hasinput(odat.Chassis): odat.Chassis = ai.Chassis
        if not hasinput(odat.Type): odat.Type = ai.ConType
        db.session.commit()

    if returned and not pulled:
        if not hasinput(container): odat.Container = ai.Container
        if odat.Istat == -1: odat.Istat = 0
        ai.Company = odat.Shipper
        ai.Jo = odat.Jo
        odat.Hstat = 2
        odat.Date2 = ai.Date
        if not hasinput(odat.Chassis): odat.Chassis = ai.Chassis
        if not hasinput(odat.Type): odat.Type = ai.ConType
        db.session.commit()

    if jexport and pulled and returned:
        if ao.Release != ai.Release:
            odat.Booking = ai.Release
            odat.BOL = ao.Release
        else:
            odat.BOL = ai.Release
        db.session.commit()