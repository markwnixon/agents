import os
import sys
import socket
from utils import getpaths

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument default is oslm')
    scac = 'oslm'

scac = scac.upper()
nt = 'remote'

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running FFF_emailread_daily for {scac} in tunnel mode: {nt}')

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
    from models8 import Interchange, Orders, Drivers, Pins, Drops, People, PortClosed
    from CCC_system_setup import websites, usernames, passwords, addpath3, imap_url, scac, companydata, nt, fromdirbase
    from email_reports import emailtxt
    from cronfuncs import conmatch
else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

import fnmatch
import subprocess
import imaplib, email
import datetime
import re
import numpy as np
from cronfuncs import newjo
from datetime import timedelta
from fpdf import FPDF

booking_p=re.compile("[1259][0123456789]{8}|EBKG[0123456789ABCDQ]{8}|EBKGQ[0123456789]{8}|[012][PHL0123456789]{9}|[S][-0123456789]{10}|[S][0123456789]{9}|[0O][0123456789VRO]{11}|NHOBJ[0123456789]{6}")

#_____________________________________________________________________________________________________________
# Switches for routines
#_____________________________________________________________________________________________________________
remit=0
gjob=1
gbook=0
kjob=0
cdata = companydata()
tcode= cdata[10]
# 0 means do not run, 1 means run normal, 2 means create new baseline
#_____________________________________________________________________________________________________________
# Hold Tunnel Open to Ensure Links
from cronfuncs import tunneltest
success = tunneltest()
#_____________________________________________________________________________________________________________

def unique(list1):
    x = np.array(list1)
    newlist=np.unique(x)
    return newlist

def get_bookings(longs):
    t=booking_p.findall(longs)
    return t

def get_body(msg):
    if msg.is_multipart():
        return get_body(msg.get_payload(0))
    else:
        return msg.get_payload(None,True)

def search(key,value,con):
    result,data=con.search(None,key,'"{}"'.format(value))
    return data

#(_, data) = CONN.search(None, '(SENTSINCE {0})'.format(date)), '(FROM {0})'.format("someone@yahoo.com") )
def search_from_date(key,value,con,datefrom):
    result,data=con.search( None, '(SENTSINCE {0})'.format(datefrom) , key, '"{}"'.format(value) )
    return data

def get_emails(result_bytes,con):
    msgs=[]
    for num in result_bytes[0].split():
        typ,data=con.fetch(num,'(RFC822)')
        msgs.append(data)
    return msgs

def get_attachments(msg):
    attachment_dir='/home/mark/alldocs/test'
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()
        if bool(file_Name):
            filePath=os.path.join(attachment_dir,file_Name)
            with open(filePath,'wb')as f:
                f.write(part.get_payload(decode=True))

def get_attachments_name(msg,this_name,att_dir):
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()
        if bool(file_Name):
            filePath=os.path.join(att_dir,this_name)
            with open(filePath,'wb')as f:
                f.write(part.get_payload(decode=True))

def get_attachments_pdf(msg,att_dir,type,contains):
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()

        if bool(file_Name):
            if type in file_Name.lower() and contains in file_Name:
                filePath=os.path.join(att_dir,file_Name)
                with open(filePath,'wb')as f:
                    f.write(part.get_payload(decode=True))

def get_attachment_filename(msg,type,contains):
    filehere=[]
    for part in msg.walk():
        if part.get_content_maintype()=='multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        file_Name=part.get_filename()
        if bool(file_Name):
            if type in file_Name.lower() and contains.lower() in file_Name.lower():
                filehere.append(file_Name)

    return filehere

def datename(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            part = response_part[1].decode('utf-8')
            msg = email.message_from_string(part)
            date=msg['Date']
            print(date)
            date=date.split('-',1)[0]
            date=date.split('+',1)[0]
            date=date.strip()
            n=datetime.datetime.strptime(date , "%a, %d %b %Y %H:%M:%S")
            adder=str(n.year)+'_'+str(n.month)+'_'+str(n.day)+'_'+str(n.hour)+str(n.minute)+str(n.second)
    return adder

def get_date(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            try:
                part = response_part[1].decode('utf-8')
                msg = email.message_from_string(part)
                date=msg['Date']
                date=date.split('-',1)[0]
                date=date.split('+',1)[0]
                date=date.strip()
                n=datetime.datetime.strptime(date , "%a, %d %b %Y %H:%M:%S")
                newdate=datetime.date(n.year,n.month,n.day)
            except:
                newdate=None
    return newdate

def get_subject(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            part = response_part[1].decode('utf-8')
            msg = email.message_from_string(part)
            subject=msg['Subject']
    return subject

def get_body_text(data):
    for response_part in data:
        if isinstance(response_part, tuple):
            part = response_part[1].decode('utf-8')
            msg = email.message_from_string(part)
            text=msg['Text']
    return text

def checkdate(emaildate,filename,txtfile):
    returnval=0
    with open(txtfile) as f:
        for line in f:
            if filename in line:
                linelist=line.split()
                date=linelist[0]
                if date != 'None':
                    datedt=datetime.datetime.strptime(date, '%Y-%m-%d')
                    datedt=datedt.date()
                    if datedt<emaildate:
                        print('File needs to be updated',datedt,date,filename)
                        returnval=1
                else:
                    print('File found, but have no date to compare')
                    returnval=1
    return returnval

def next_business_day(date, jx):
    next_day = date
    kx = 0
    for ix in range(15):
        next_day = next_day + timedelta(days=1)
        pdat = PortClosed.query.filter(PortClosed.Date==next_day).first()
        if pdat is None:
            kx += 1
            if kx == jx: return next_day

if 1==1:

    def makepdf(body, date):
        sdate = f'Email Date: {date}'
        docname = f'global_email_{date}.pdf'
        docname = docname.replace('-','')
        fromdir = f'{fromdirbase}/incoming/tjobs'
        fromfile = f'{fromdir}/{docname}'
        slist = os.listdir(fromdir)
        print(slist)
        if docname not in slist:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=10)
            pdf.cell(200, 10, txt=sdate, ln=1, align='L')
            newbody = []
            for line in body.splitlines():
                line = line.strip()
                newbody.append(line)
            for jx, line in enumerate(newbody):
                line = line.strip()
                print(jx, line)
                pdf.cell(200, 10, txt=line, ln=jx + 2, align='L')
            try:
                pdf.output(fromfile)
            except:
                print('Could not create an output file for this one')
                docname = 'fail'
            if docname != 'fail':
                copyline = f'scp {fromfile} {websites["ssh_data"] + "vSource"}'
                print('copyline=', copyline)
                os.system(copyline)
        return docname

    if remit>0:

        msgs=get_emails(search('FROM','ReportServer@KnightTrans.com',con),con)
        att_dir='/home/mark/alldocs/emailextracted/knightremits'
        for j,msg in enumerate(msgs):
            adder=datename(msg)
            print(adder)
            this_name='Remittance'+'_'+adder+'.pdf'
            #print(get_body(email.message_from_bytes(msg[0][1])))
            raw=email.message_from_bytes(msg[0][1])
            get_attachments_name(raw,this_name,att_dir)

        for file2 in os.listdir(att_dir):
            if fnmatch.fnmatch(file2, '*.pdf'):
                #Check to see if already in database:
                base=os.path.splitext(file2)[0]
                tp=subprocess.check_output(['pdf2txt.py', '-o', os.path.join(att_dir,base+'.txt'), os.path.join(att_dir,file2)])



#_____________________________________________________________________________________________________________
# Subroutine to grab bookings from ABE for Global work and put into the database on website
#_____________________________________________________________________________________________________________
    if gjob>0:
        if gjob==1:
            dayback=16
        if gjob==2:
            dayback=450
        datefrom = (datetime.date.today() - datetime.timedelta(dayback)).strftime("%d-%b-%Y")
        print(datefrom)
        username = usernames['infh']
        password = passwords['infh']
        con = imaplib.IMAP4_SSL(imap_url)
        con.login(username,password)
        con.select('INBOX')
        msgs=get_emails(search_from_date('FROM','@gblna.com',con,datefrom),con)
        # msgs=get_emails(search('FROM','aalsawi@gblna.com',con),con)
        con.close()
        con.logout()

        bookings=[]
        norepeat=[]
        for j,msg in enumerate(msgs):
            raw=email.message_from_bytes(msg[0][1])
            body=get_body(raw)
            getdate=get_date(msg)
            if 1 == 1:
                try:
                    body=body.decode('utf-8')
                    skipit = 1
                except:
                    print(f'body not decoded:{body}')
                    skipit = 0
                if skipit:
                    docname = makepdf(body, getdate)
                    blist=get_bookings(body)
                    bodylines = body.splitlines()
                    if blist:
                        print(f'{getdate} {blist}')
                        for b in blist:
                            b=b.strip()
                            b = b.replace('-', '')
                            size = '40'
                            for line in bodylines:
                                if b in line and "40'" in line:
                                    print(f'Booking {b} is a 40')
                                    size = '40'
                                if b in line and "20'" in line:
                                    print(f'Booking {b} is a 20')
                                    size = '20'
                            if b not in norepeat:
                                booktriplet=[b,getdate,getdate,size,docname]
                                bookings.append(booktriplet)
                                norepeat.append(b)
                            else:
                            #find the existing booking and replace the second date
                                for book in bookings:
                                    if book[0]==b:
                                        book[2]=getdate

                else:
                    print('Bad decode on',getdate)


        try:
            with open(addpath3(f'emaildocs/global_jobs_{scac}.txt')) as f:
                longs=f.read()
            f.close()
        except:
            longs=''

        if gjob==1:
            ot='a'
        if gjob==2:
            ot='w'

        with open(addpath3(f'emaildocs/global_jobs_{scac}.txt'),ot) as f:
            for book in bookings:
                b=book[0]
                d1=book[1].strftime('%Y-%m-%d')
                d2=book[2].strftime('%Y-%m-%d')
                pulldate = book[1] + timedelta(1)
                indate = next_business_day(pulldate, 1)
                doc = book[4]
                try:
                    size = book[3]
                except:
                    size = '40'
                if gjob==2:
                    print('Adding',b,d1,d2)
                    f.write(b+' '+d1+' '+d2+'\n')

                if gjob==1:
                    bdat=Orders.query.filter(Orders.Booking==b).first()
                    pdat = People.query.filter(People.Company == 'Global Business Link').first()
                    bid = pdat.id
                    ldat = Drops.query.filter(Drops.Entity == 'Global Business Link').first()
                    lid = ldat.id
                    ddat = Drops.query.filter(Drops.Entity == 'Baltimore Seagirt').first()
                    did = ddat.id
                    if size == '40': putsize = '''40' GP 9'6"'''
                    if size == '20': putsize = '''20' GP 8'6"'''
                    if bdat is None and b not in longs:
                        print('Adding',b,d1,d2)
                        f.write(b+' '+d1+' '+d2+'\n')
                        sdate=getdate.strftime('%Y-%m-%d')
                        jtype=tcode + 'T'
                        nextjo=newjo(jtype,sdate)
                        load='G'+nextjo[-5:]
                        order='G'+nextjo[-5:]
                        if doc == 'fail': doc = None
                        print(doc)

                        input = Orders(Status='AO', Jo=nextjo, HaulType='Dray Export DP', Order=order, Bid=bid, Lid=lid,
                                       Did=did, Company2='Global Business Link', Location=None, BOL=None, Booking=b,
                                       Container=None, Driver=None, Pickup=None, Delivery=None, Amount='370.00',
                                       Date=pulldate, Time=None, Time3=None, Date2=indate, Time2=None, PaidInvoice=None,
                                       Source=doc, Description=None, Chassis=None, Detention=None,
                                       Storage=None, Release=0, Company='Baltimore Seagirt', Seal=None,
                                       Shipper='Global Business Link', Type=putsize, Label=None,
                                       Dropblock2='Global Business Link\n4000 Coolidge Ave K\nBaltimore, MD 21229',
                                       Dropblock1='Baltimore Seagirt\n2600 Broening Hwy\nBaltimore, MD 21224',
                                       Commodity=None, Packing=None, Links=None, Hstat=-1, Istat=-1, Proof=None,
                                       Invoice=None, Gate=None, Package=None, Manifest=None, Scache=0, Pcache=0,
                                       Icache=0, Mcache=0, Pkcache=0, QBi=None, InvoTotal='370.00', Truck=None,
                                       Dropblock3=None, Date3=pulldate, Location3=None, InvoDate=None, PaidDate=None,
                                       PaidAmt=None, PayRef=None, PayMeth=None, PayAcct=None, BalDue=None, Payments=None, Quote=None,
                                       Date4=None,Date5=None,Date6=None,RateCon=None,Rcache=0,Proof2=None,Pcache2=0,Emailjp=None,
                                       Emailoa=None,Emailap=None,Saljp=None,Saloa=None,Salap=None,Date7=None,SSCO=None,Date8=indate,Ship=None,Voyage=None)


                        db.session.add(input)
                        db.session.commit()
                    else:
                        print('                Skipping',book[0],book[1],book[2])

today = datetime.date.today()
cutoffdate = today - datetime.timedelta(120)
######Change booking of job for container if pulled under different booking#####
cdata = Orders.query.filter( (Orders.Shipper == 'Global Business Link') & (Orders.Hstat == 2) & (Orders.Istat < 3) & (Orders.Date > cutoffdate) ).all()
for cdat in cdata:
    bk = cdat.Booking
    con = cdat.Container
    jo = cdat.Jo
    idata = Interchange.query.filter( (Interchange.Container == con) & (Interchange.Date > cutoffdate) ).all()
    print(bk, con, len(idata))
    if len(idata) == 2:
        idat1 = idata[0]
        idat2 = idata[1]
        type1 = idat1.Type
        type2 = idat2.Type
        if type1 == 'Load In':
            bkin = idat1.Release
            bkout = idat2.Release
        else:
            bkin = idat2.Release
            bkout = idat1.Release

        if bkin == bkout:
            print(f'For container {con} the bookings match out and in')
        else:
            print(f'For container {con} the out on {bkout} and in on {bkin}')
            if bk == bkout:
                print(f'Need to change Jo {jo} with container {con} from {bk} to {bkin}')
                cdat.Booking = bkin
                cdat.BOL = bkout
                db.session.commit()




#####Now kill Global Bookings placed in system that are over 8 days old...unlikely to be used.
kdata = Orders.query.filter( (Orders.Shipper == 'Global Business Link') & (Orders.Hstat <= 0)).all()
ksid = []
isid = []

for kdat in kdata:
    kdate = kdat.Date
    daysover = today - kdate
    daysover = daysover.days
    if daysover > 12:
        print(f'For JO {kdat.Jo} with booking {kdat.Booking} and Hstat {kdat.Hstat} from {kdate} to {today} no pull for {daysover} days')
        check = Interchange.query.filter( (Interchange.Release == kdat.Booking) & (Interchange.Date > cutoffdate) ).all()
        if check != []:
            print(f'Found a booking pulled {kdat.Booking} with no match in the orders for Global')
            isid.append(kdat.id)
            for ck in check:
                print(f'Found Interchange for {ck.Release} and {ck.Container}')
        else:
            print(f'Confirmed for Killing booking {kdat.Booking} from {kdat.Date} to {today} no pull for {daysover} days')
            ksid.append(kdat.id)

print(f'Killing these jobs : {ksid}')
print(f'Need to investigate: {isid}')
for ki in ksid:
    Orders.query.filter(Orders.id == ki).delete()
db.session.commit()



if nt == 'remote': tunnel.stop()