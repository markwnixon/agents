import datetime
from remote_db_connect import db
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

    okat = Orders.query.get(oder)
    bkout = okat.Booking
    con = okat.Container
    htype = okat.HaulType
    lbdate = okat.Date3 - timedelta(120)
    ntick = 0
    kdat = None
    nbk = 1

    #If export check for multiple bookings and control accordingly
    if 'Export' in htype:
        #Only run if have a legitimate booking number.
        if len(bkout) > 5:
            # Make sure start from the base booking without dashes:
            if '-' in bkout:
                bklist = bkout.split('-')
                bkout = bklist[0]
                if len(bkout) < 7: bkout = 'NoBook'
            edata = Orders.query.filter((Orders.HaulType.contains('Export')) & (Orders.Booking.contains(bkout)) & (Orders.Date > lbdate)).all()
            nbk = len(edata)
            multibooking = 1
            if nbk > 1:
                multibooking = 0
                #Check to make sure they all have the same base booking.
                jo_multibook = []
                for edat in edata:
                    tbooking = edat.Booking
                    tbklist = tbooking.split('-')
                    tbook = tbklist[0]
                    if tbook == bkout:
                        multibooking += 1
                        jo_multibook.append(edat.Jo)

                if multibooking < 2:
                    jo_multibook = []
                    multibooking = 0
                    nbk = 1



                if multibooking > 1:
                    ix = 1
                    for edat in edata:
                        jo = edat.Jo
                        if jo in jo_multibook:
                            bklabel = f'{bkout}-{ix}'
                            edat.Booking = bklabel
                            ix += 1
                    db.session.commit()

                    # Now have to update and relabel the Interchange tickets to match, and make sure the dashes match the orders only if the base bookings match
                    ix = 1
                    idata = Interchange.query.filter((Interchange.Release.contains(bkout)) & (Interchange.Date > lbdate) & (Interchange.Type == 'Empty Out')).all()
                    if idata:
                        for jx, idat in enumerate(idata):
                            current_booking = idat.Release
                            base_nodash = current_booking.split('-')
                            release_nodash = base_nodash[0]
                            if bkout == release_nodash:
                                bklabel = f'{release_nodash}-{ix}'
                                idat.Release = bklabel
                                container = idat.Container
                                mdat = Interchange.query.filter((Interchange.Container == container) & (Interchange.Date > lbdate) & (Interchange.Type == 'Load In')).first()
                                if mdat is not None:
                                    mdat_booking = mdat.Release
                                    mbase_nodash = mdat_booking.split('-')
                                    mrelease_nodash = mbase_nodash[0]
                                    if bkout == mrelease_nodash:
                                        mbklabel = f'{mrelease_nodash}-{ix}'
                                        mdat.Release = mbklabel
                                ix += 1
                        db.session.commit()

                    #Now reset the order using the relabeled bookings that have dashes:
                    edata = Orders.query.filter((Orders.HaulType.contains('Export')) & (Orders.Booking.contains(bkout)) & (Orders.Date > lbdate)).all()
                    for edat in edata:
                        jo = edat.Jo
                        if jo in jo_multibook:
                            whole_booking = edat.Booking
                            jdat = Interchange.query.filter((Interchange.Release == whole_booking) & (Interchange.Date > lbdate) & (Interchange.Type == 'Empty Out')).first()
                            if jdat is not None:
                                jo = edat.Jo
                                shipper = edat.Shipper
                                jdat.Jo = jo
                                jdat.Company = shipper
                                con = jdat.Container
                                edat.Container = con
                                edat.Chassis = jdat.Chassis
                                edat.Hstat = Gate_Match(con, lbdate, multibooking, 'Export', edat)
                                db.session.commit()
                            else:
                                edat.Container = ''
                                edat.Chassis = ''
                                edat.Hstat = 0
                                db.session.commit()


        else:
            err = ['Cannot create or update an export without a booking number']



    if nbk == 1:
        if hasinput(con):
            idata = Interchange.query.filter((Interchange.Container == con) & (Interchange.Date > lbdate)).all()
            ntick = len(idata)
        if hasinput(bkout):
            kdat = Interchange.query.filter((Interchange.Release == bkout) & (Interchange.Type == 'Empty Out') & (Interchange.Date > lbdate)).first()

        #print(f'There are {ntick} interchange tickets based on container search')
        if ntick == 2:
            test = 1
            if 'Out' in idata[0].Type:
                idat0 = idata[0]
                idat1 = idata[1]
            elif 'Out' in idata[1].Type:
                idat1 = idata[0]
                idat0 = idata[1]
            else:
                test = 0
                ###print('Failed test of proper pairing')
            if test:
                #print(f'{idat0.Type}: {idat0.Release} {idat0.Container}')
                #print(f'{idat1.Type}: {idat1.Release} {idat1.Container}')
                # Check to see if pairing completed and this is only Order for that container (in case duplicated)
                if 'Out' in idat0.Type and 'In' in idat1.Type:
                    allorders = Orders.query.filter((Orders.Container == con) & (Orders.Date3 > lbdate)).all()
                    if len(allorders) == 1:
                        jo = okat.Jo
                        shipper = okat.Shipper
                        idat0.Status = 'IO'
                        idat1.Status = 'IO'
                        idat0.Jo = jo
                        idat1.Jo = jo
                        idat0.Company = shipper
                        idat1.Company = shipper
                #If this is an import then the release will not be included in interchange ticket so do not update the order or it will be erased
                if 'Export' in okat.HaulType:
                    okat.Booking = idat0.Release
                    okat.BOL = idat1.Release
                okat.Chassis = idat0.Chassis
                okat.ConType = idat0.ConType
                okat.Date = idat0.Date
                okat.Date2 = idat1.Date
                okat.Hstat = 2
                db.session.commit()

        if ntick == 1:
            ikat = idata[0]
            con = ikat.Container
            release = ikat.Release
            movetyp = ikat.Type
            if movetyp == 'Load Out':
                #This should be an import, container will already be edited input
                okat.Chassis = ikat.Chassis
                okat.ConType = ikat.ConType
                okat.Date = ikat.Date
                okat.Hstat = 1
                ikat.Status = 'BBBBBB'
                db.session.commit()
            if movetyp == 'Empty Out':
                okat.Container = con
                okat.Chassis = ikat.Chassis
                okat.ConType = ikat.ConType
                okat.Booking = ikat.Release
                okat.Date = ikat.Date
                okat.Hstat = 1
                ikat.Company = okat.Shipper
                ikat.Jo = okat.Jo
                ikat.Status = 'BBBBBB'
                db.session.commit()
            if movetyp == 'Empty In':
                okat.Date2 = ikat.Date
                okat.Hstat = 2
                ikat.Status = 'No Load Out'
                db.session.commit()
            if movetyp == 'Load In':
                okat.Date2 = ikat.Date
                okat.Hstat = 2
                okat.BOL = ikat.Release
                ikat.Status = 'No Empty Out'
                db.session.commit()

        if ntick == 0 and kdat is not None:
            ###print('Doing the most dangerous update')
            #If only have no tickets based on container and have an empty out based on booking do that update
            con = kdat.Container
            movetyp = kdat.Type
            ###print(f'Performing update based on interchange empty out give con {con} and movetyp {movetyp}')
            if movetyp == 'Empty Out':
                okat.Container = con
                okat.Chassis = kdat.Chassis
                okat.ConType = kdat.ConType
                okat.Date = kdat.Date
                kdat.Company = okat.Shipper
                kdat.Jo = okat.Jo
                if okat.Hstat is None: okat.Hstat = 1
                elif okat.Hstat < 3: okat.Hstat = 1
            #And now we have to complete the assignment based on the container number of the first interchange
                ingate = Interchange.query.filter((Interchange.Container == con) & (Interchange.Type == 'Load In') & (Interchange.Date > lbdate)).first()
                if ingate is not None:
                    okat.BOL = ingate.Release
                    okat.Date2 = ingate.Date
                    okat.Hstat = 2
                    ingate.Company = okat.Shipper
                    ingate.Jo = okat.Jo
                    ingate.Status = 'IO'
                    kdat.Status = 'IO'
                db.session.commit()
    return