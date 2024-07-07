import os
import sys
import imaplib, email
import datetime
import re
import numpy as np
from datetime import timedelta
import socket
from utils import getpaths
import importlib
from utils import hasinput

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
except:
    print('Must have at least one argument...FELA or OSLM')
    scac = 'oslm'

scac = scac.upper()
nt = 'remote'

if scac == 'OSLM' or scac == 'FELA':
    print(f'Running BBB_dray_ARcheck for {scac}')

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
    from models8 import Orders, Interchange, Pins

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

if scac != 'nogo':

    print(f'Running Planner for {scac}')
    from CCC_system_setup import companydata, usernames, passwords, imap_url
    from cronfuncs import tunneltest
    success = tunneltest()

    cdata = companydata()
    tcode= cdata[10]

    booking_p=re.compile("[1259][0123456789]{8}|[E][BKG0123456789Q]{11}|[012][PHL0123456789]{9}|[S][-0123456789]{10}|[S][0123456789]{9}|[0O][0123456789VRO]{11}")
    container_p=re.compile("[A-Z,a-z]{4}[0123456789]{7}[\s]")

    #Context = 0 for planning of today, contaxt =1 for planning of tomorrow
    context = 0

    today = datetime.datetime.today()
    today = today.date()
    lastdow = today
    if context == 1:
        today = today + timedelta(1)

    cutoff = today - timedelta(7)
    #cutoff = cutoff.date()
    cuthigh = today + timedelta(7)
    #cuthigh = cuthigh.date()
    tomorrow = today + timedelta(1)
    #today = today.date()
    #tomorrow = tomorrow.date()
    dow1 = today.strftime('%a')
    dow2 = tomorrow.strftime('%a')
    ##print(f'Key dates are Today:{today}, Tomorrow: {tomorrow}, Low Cut:{cutoff}, High Cut:{cuthigh}, dow1: {dow1} dow2:{dow2}')

    def fixlines(addr):
        addr = addr.replace('First Eagle Logistics Inc', 'FEL Warehouse')
        addr = addr.replace('Global Business Link', 'Global Warehouse')
        addr = addr.strip()
        a1 = addr.splitlines()
        a1lines = ''
        for i in range(len(a1)): a1lines = a1lines + a1[i] + ', '
        a1lines = a1lines.strip()
        a1l = a1lines[:-1]
        return a1l

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
                ##print(date)
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
                            ##print('File needs to be updated',datedt,date,filename)
                            returnval=1
                    else:
                        ##print('File found, but have no date to compare')
                        returnval=1
        return returnval

    if 1==1:
        gjob=1
    #-____________________________________________________________________________________________________________
    # Subroutine to grab bookings from ABE for Global work and put into the database on website
    #_____________________________________________________________________________________________________________
        if gjob>0:
            if gjob==1:
                dayback=10
            datefrom = (datetime.date.today() - datetime.timedelta(dayback)).strftime("%d-%b-%Y")
            ##print(datefrom)
            username = usernames['infh']
            password = passwords['infh']
            print(f'imapurl: {imap_url} and user {username} and Pass {password}')
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
                #print(getdate)
                lastdate = getdate
                lasttom = lastdate + timedelta(1)
                lastdow = lasttom.strftime('%a')
                try:
                    body=body.decode('utf-8')
                    lastbody = body
                    blist=get_bookings(body)
                    if blist:
                        #print(f'{getdate} {blist}')
                        for b in blist:
                            b=b.strip()
                            b = b.replace('-', '')
                            if b not in norepeat:
                                booktriplet=[b,getdate,getdate]
                                bookings.append(booktriplet)
                                norepeat.append(b)
                            else:
                            #find the existing booking and replace the second date
                                for book in bookings:
                                    if book[0]==b:
                                        book[2]=getdate

                except:
                    print('Bad decode on',getdate)

            #Make sure the Orders are up to date with the Interchange

            #Elevate Hstat if both Interchange cards here and change booking to the booking in if changed
            odata = Orders.query.filter((Orders.Hstat < 2) & (((Orders.Date >= cutoff) & (Orders.Date <= cuthigh)) | ((Orders.Date2 >= cutoff) & (Orders.Date2 <= cuthigh))) ).all()
            for odat in odata:
                hstat = odat.Hstat
                bk = odat.Booking
                if hstat == 1:
                    kdat = Interchange.query.filter(Interchange.Release == bk).first()
                    if kdat is not None:
                        cni = kdat.Container
                        cno = odat.Container
                        if len(cno) != 11:
                            odat.Container = kdat.Container
                            odat.Type = kdat.ConType
                            odat.Chassis = kdat.Chassis

                        idata = Interchange.query.filter(Interchange.Container == cni).all()
                        for idat in idata:
                            if idat.Type == 'Load In':
                                #print(f'{cni} {idat.Type} {odat.Hstat}')
                                oldbook = odat.Booking
                                odat.Booking = idat.Release
                                odat.BOL = oldbook
                                odat.Hstat = 2
                            if idat.Type == 'Empty In':
                                odat.Hstat = 2
            db.session.commit()


            odata = Orders.query.filter((Orders.Hstat < 2) & (((Orders.Date >= cutoff) & (Orders.Date <= cuthigh)) | ((Orders.Date2 >= cutoff) & (Orders.Date2 <= cuthigh))) ).all()
            for odat in odata:
                #print(f'Working on {odat.Shipper} {odat.Booking} {odat.Container} with Hstat {odat.Hstat}')
                hstat = odat.Hstat
                if hstat == 1:
                    cn = odat.Container
                    if len(cn) != 11:
                        idat = Interchange.query.filter(Interchange.Release == odat.Booking).first()
                        if idat is not None:
                            odat.Container = idat.Container
                            odat.Type = idat.ConType
                            odat.Chassis = idat.Chassis
                            db.session.commit()
                    #print(f'This container is {cn}')

            joblines = [f'*Global {lasttom} {lastdow}*']
            bkinlines = ['*Global Load In Bookings*']
            bkoutlines = ['*Global Empty Out Bookings*']
            incon = None
            inbook = None
            inchas = None
            intext = None
            for line in lastbody.splitlines():
                t = booking_p.findall(line)
                if t != []:
                    ##print(f'booking in this line is {t[0]}')
                    bk = t[0]
                    c = container_p.findall(line)
                    line = line.replace('#', '')
                    for bk in t:
                        line = line.replace(bk, f'*{bk}*')
                    idat = Interchange.query.filter(Interchange.Release == bk).first()
                    if idat is not None:
                        inchas = idat.Chassis
                        container = idat.Container
                    if c == [] and 'container' in line.lower():
                        #Just does not know the container number
                        if idat is not None:
                            line = line.replace('Container', idat.Container)
                            line = line.replace('container', idat.Container)
                            container = idat.Container
                            c = container_p.findall(line)

                    if c != []:
                        line = line.replace('Container', '')
                        if 'will be ready' in line.lower(): ready = ''
                        else: ready = 'Ready'
                        if "40'" in line: size = '40'
                        elif "20'" in line: size = '20'
                        elif "45'" in line: size = '45'
                        else: size = '?'
                        for cn in c:
                            cn = cn.strip()
                            line = line.replace(cn, f'*{cn}*')
                            line = line.replace('*   *','  ')
                            line = line.replace('*  *', '  ')
                            line = line.replace('* *', '  ')
                        print(f'container on this line is {cn}')
                        print(f'booking on this line is {bk}')
                        print(f'chassis for this load in is {inchas}')
                        intext = f'Load In: *{bk} {cn}* (Global {size} customs)'
                        inbook = bk
                        incon = cn
                        joblines.append(line)
                        #joblines.append(f'Load In: *{t[0]} {container}* {size} {ready}')
                        #print('Global Load In Booking',bk)
                        bkinlines.append(bk)
                    else:
                        joblines.append(line)
                        #joblines.append(f'Empty Out: *{t[0]}* {size}')
                        joblines.append(' ')
                        #print('Global Empty Out Booking', bk)
                        bkoutlines.append(bk)
                        if "40'" in line: size = '40'
                        elif "20'" in line: size = '20'
                        elif "45'" in line: size = '45'
                        else: size = '?'
                        outtext = f'Empty Out: *{bk}* (Global {size})'
                        outbook = bk
                        pdat = Pins.query.filter(Pins.InCon == incon).first()
                        if pdat is None:
                            input = Pins(Date=lasttom, Driver=None, InBook=inbook, InCon=incon, InChas=inchas,
                                         InPin='0', OutBook=outbook, OutCon=None, OutChas=inchas, OutPin='0',
                                         Unit=None, Tag=None, Phone=None, Intext=intext, Outtext=outtext, Notes=None, Timeslot=0)
                            db.session.add(input)
                            db.session.commit()

        joblines.append(f'*Other Jobs {dow1}*')
        tomdev = [f'*Pulls Today for Delivery {dow2}*']
        print(f'Looking at Orders from')
        odata = Orders.query.filter(((Orders.Hstat < 2) | (Orders.Hstat == None)) & (((Orders.Date >= cutoff) & (Orders.Date <= cuthigh)) | ((Orders.Date3 >= cutoff) & (Orders.Date3 <= cuthigh))) ).all()

        for odat in odata:
            od = odat.Order
            sh = odat.Shipper
            bk = odat.Booking
            bol = odat.BOL
            cn = odat.Container
            tp = odat.Type
            dt = odat.Date
            dtd = odat.Date2
            hstat = odat.Hstat
            if hstat is None: hstat = 0
            addr1 = odat.Dropblock1
            addr2 = odat.Dropblock2
            a1l = fixlines(addr1)
            a2l = fixlines(addr2)

            if hstat != 1:
                if cn is None:
                    type = 'export'
                else:
                    if len(cn) < 11:
                        type = 'export'
                    else:
                        type = 'import'

                ht = odat.HaulType
                if 'export' in ht: type = 'export'
                if 'import' in ht: type = 'import'

            elif hstat == 1:
                if bol == bk: type = 'import'
                else: type = 'export'

                ht = odat.HaulType
                if 'export' in ht: type = 'export'
                if 'import' in ht: type = 'import'

            print(f'For JO {odat.Jo}  type: {type}')

            if 'Global Business' not in sh or 'outside' in od.lower():
                if 'Knightx' not in sh:
                    if 'Global Business' in sh: sh = f'Global {od}'
                    if 'FEL Ocean' in sh: sh = f'FEL {od}'
                    if hstat < 1:
                        if dt == today:
                            if type == 'import':
                                joblines.append(f'Load Out: *{bk} {cn}* ({tp} {sh})')
                                joblines.append(f'{a2l}')
                                joblines.append(' ')
                            elif type == 'export':
                                joblines.append(f'Empty Out: *{bk}* ({tp} {sh})')
                                joblines.append(f'Deliver to {a2l}')
                                joblines.append(' ')
                        elif dt == tomorrow:
                            if type == 'import':
                                tomdev.append(f'Load Out: *{bk} {cn}* ({tp} {sh})')
                                tomdev.append(' ')
                            elif type == 'export':
                                tomdev.append(f'Empty Out: *{bk}* ({tp} {sh})')
                                tomdev.append(' ')
                    if hstat == 1:
                        #print(f'booking with dtd <= tomorrow: {bk} type {type} {cn} {dtd}')
                        if dtd <= tomorrow:

                            if type == 'import':
                                joblines.append(f'Empty In: *{cn}* ({tp} {sh})')
                                joblines.append(f'{a2l}')
                            elif type == 'export':
                                joblines.append(f'Load In: *{bk} {cn}* ({tp} {sh})')
                                joblines.append(f'{a2l}')
                                joblines.append(' ')

        ##print(f'Message on {lastdate} in lastbody is: {lastbody}')
        print('')
        print('')
        print(f'***********************************{scac}**************************************************')
        print(f'***********************************{scac}**************************************************')
        print(f'***********************************{scac}**************************************************')
        print(f'***********************************{scac}**************************************************')
        for line in joblines:
            print(line)


        for line in tomdev:
            print(line)

        for line in bkinlines:
            print(line)

        for line in bkoutlines:
            print(line)



    tunnel.stop()