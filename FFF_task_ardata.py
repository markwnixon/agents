from datetime import datetime, timedelta
import os
import sys
from PyPDF2 import PdfFileReader, PdfFileWriter, PdfFileMerger
import socket
from utils import getpaths
import imaplib, email
from email.header import decode_header
from email.utils import parseaddr
from email.utils import parsedate_to_datetime
import html2text

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    scac = 'oslm'

scac = scac.upper()
nt = 'remote'
#nt = 'local'

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

    from remote_db_connect import db
    if nt == 'remote': from remote_db_connect import tunnel
    from models8 import Interchange, Orders, Ardata, SumInv, People
    from CCC_system_setup import websites, usernames, passwords, addpath3, addpath, addpaths, imap_url
    from email_reports import emailtxt
    from cronfuncs import conmatch
else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

from utils import hasinput
from cronfuncs import tunneltest, Order_Container_Update

if nt == 'remote':
    success = tunneltest()

if scac == 'OSLM':
    username_list = [usernames['invo'], usernames['serv'], usernames['invo']]
    password_list = [passwords['invo'], passwords['serv'], passwords['invo']]
    boxlist = ['SENT', 'SENT', 'INBOX']
    skiplist = []
elif scac == 'FELA':
    username_list = [usernames['mnix'], usernames['info']]
    password_list = [passwords['mnix'], passwords['info']]
    boxlist = ['INBOX.Sent', 'INBOX']
    skiplist = []
elif scac == 'NEVO':
    username_list = [usernames['serv'], usernames['info']]
    password_list = [passwords['serv'], passwords['info']]
    boxlist = ['SENT', 'SENT']
    skiplist = ['invoices@thunderfunding']

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





def remove_sig(body):
    text = ''
    start_process = 1
    bodylines = body.splitlines()
    for line in bodylines:
        if 'img src' in line:
            start_process = 0
        if start_process: text += line
        if len(text) > 2000: break
    if len(text) > 1996: text = text[0:1995]
    return text

def make_ea_list(tor):
    try:
        torlist = tor.strip().split(',')
    except:
        return []
    elist = []
    for newtor in torlist:
        #print(f'The newtor is {newtor}')
        name, emailaddr = parseaddr(newtor)
        #print(f'The newtor name and email is {name}, {emailaddr}')
        elist.append(emailaddr)
    return elist


def get_reminder_emails(customer, box):
    cdat = People.query.filter((People.Company == customer) & (People.Ptype == 'Trucking')).first()
    if cdat is not None:
        emaillist = [cdat.Email, cdat.Associate1, cdat.Associate2]
        emlist = []
        for em in emaillist:
            if hasinput(em): emlist.append(em)
        emu = set(emlist)
        emlist = list(emu)
        print(f'For emaillist {emaillist}, emlist {emlist}')
        for em in emlist:
            if em not in skiplist:
                status, messages = imap.search(None, '(TO "{}")'.format(em))
                email_ids = messages[0].split()
                #print(f'For recipient {em} there are {len(email_ids)} emails in {box} folder pertaining to customer {customer}.')
                for email_id in email_ids:
                    status, msg_data = imap.fetch(email_id, "(RFC822)")
                    email_message = email.message_from_bytes(msg_data[0][1])
                    # Get the subject of the email
                    subject, encoding = decode_header(email_message["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    #print(f'The {customer} and email to {em}, the subject is: {subject}')
                    if 'open balance' in subject.lower() or 'report' in subject.lower():
                        #This an email we looking for...
                        # Get the sender's email address
                        sender = parseaddr(email_message.get("From"))[1]
                        to_recipients = email_message.get("To")
                        cc_recipients = email_message.get("Cc")
                        # Get the email body
                        body = ''
                        if email_message.is_multipart():
                            #print('The email is multipart')
                            for part in email_message.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))

                                if "attachment" not in content_disposition:
                                    #print(f'The content disposition is {content_disposition}')
                                    try:
                                        body_part = part.get_payload(decode=True).decode(
                                            part.get_content_charset() or "utf-8")
                                    except:
                                        body_part = part

                                    if content_type == "text/plain":
                                        body += body_part
                                    elif content_type == "text/html":
                                        # print(body_part)
                                        body = remove_sig(body_part)
                                        body = html_to_plain_text(body)
                                        pass
                        else:
                            #print('The email is not multipart')
                            body = email_message.get_payload(decode=True).decode(
                                email_message.get_content_charset() or "utf-8")

                        date_str = email_message.get("Date")
                        date_object = parsedate_to_datetime(date_str)
                        thisdate = date_object.date()
                        thistime = date_object.time()
                        #print(f'Date: {str(thisdate)}')
                        #print(f'Time: {str(thistime)}')

                        # Get the email ID
                        email_id = email_id.decode()
                        # Print or process the email details
                        #print(f'For container {container}')
                        #print("Email ID:", email_id)
                        #print("Subject:", subject)
                        #print("From:", sender)
                        tolist = make_ea_list(to_recipients)
                        #print("To:", f'{tolist}')
                        cclist = make_ea_list(cc_recipients)
                        #print("CC:", f'{cclist}')
                        #print("Body:", body)
                        #print(f'The length of body is {len(body)}')
                        itype = 'Report'
                        if 're:' in subject.lower(): itype = 'Report Response'
                        #print(f' This email is of email type: {itype}')
                        #print("----------------------")

                        ardat = Ardata.query.filter(Ardata.Mid == email_id).first()
                        if ardat is None:
                            input = Ardata(Etitle=subject, Ebody=body, Emailto=f'{tolist}', Emailcc=f'{cclist}',
                                           Sendfiles=None, Sendasfiles=None, Jolist=None,
                                           Emailtype=f'{itype}', Mid=f'{email_id}', Customer=customer,
                                           Container=None, Date1=thisdate, Datelist=None, From=sender, Box=box)
                            db.session.add(input)
                            db.session.commit()
        return


def html_to_plain_text(html_content):
    # Create an instance of the HTML2Text class
    h = html2text.HTML2Text()

    # Convert HTML to plain text
    plain_text = h.handle(html_content)

    return plain_text




def get_invoice_emails(container, summary, box):
    if summary is not None:
        status, messages = imap.search(None, '(SUBJECT "{}")'.format(summary))
    else:
        status, messages = imap.search(None, '(SUBJECT "{}")'.format(container))

    email_ids = messages[0].split()
    print(f'There are {len(email_ids)} emails in sent folder pertaining to container {container}.')
    # Iterate through the list of email IDs
    for email_id in email_ids:
        try:
            # Fetch the email using the ID
            status, msg_data = imap.fetch(email_id, "(RFC822)")
            email_message = email.message_from_bytes(msg_data[0][1])
            # Get the subject of the email
            subject, encoding = decode_header(email_message["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8")

            if 'invoice' in subject.lower() or 'package' in subject.lower():
                # Get the sender's email address
                sender = parseaddr(email_message.get("From"))[1]
                to_recipients = email_message.get("To")
                cc_recipients = email_message.get("Cc")

                # Get the email body
                body = ''
                if email_message.is_multipart():
                    #print('The email is multipart')
                    for part in email_message.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))

                        if "attachment" not in content_disposition:
                            #print(f'The content disposition is {content_disposition}')
                            try:
                                body_part = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
                            except:
                                body_part = part

                            if content_type == "text/plain":
                                body += body_part
                            elif content_type == "text/html":
                                #print(body_part)
                                body = remove_sig(body_part)
                                body = html_to_plain_text(body)
                                pass
                else:
                    #print('The email is not multipart')
                    body = email_message.get_payload(decode=True).decode(email_message.get_content_charset() or "utf-8")


                date_str = email_message.get("Date")
                #print(f' The date string to pars is {date_str}')
                date_object = parsedate_to_datetime(date_str)
                thisdate = date_object.date()
                thistime = date_object.time()
                #print(f'Date: {str(thisdate)}')
                #print(f'Time: {str(thistime)}')

                # Get the email ID
                email_id = email_id.decode()
                # Print or process the email details
                #print(f'For container {container}')
                ##print("Email ID:", email_id)
                #print("Subject:", subject)
                #print("From:", sender)
                tolist = make_ea_list(to_recipients)
                #print("To:", f'{tolist}')
                cclist = make_ea_list(cc_recipients)
                #print("CC:", f'{cclist}')
                #print("Body:", body)
                #print(f'The length of body is {len(body)}')
                itype = 'Invoice'
                if 're:' in subject.lower(): itype = 'Invoice Response'
                #print(f' This email is of email type: {itype}')
                #print("----------------------")

                ardat = Ardata.query.filter(Ardata.Mid==email_id).first()
                if ardat is None:
                    input = Ardata(Etitle = subject,Ebody = body, Emailto=f'{tolist}', Emailcc=f'{cclist}', Sendfiles=None, Sendasfiles=None, Jolist=f'[{odat.Jo}]', Emailtype=f'{itype}', Mid=f'{email_id}', Customer=odat.Shipper, Container=container, Date1=thisdate, Datelist=None, From=sender, Box=box)
                    db.session.add(input)
                    db.session.commit()

        except:
            print("An error occurred")
    return

#Set Up Data for Finding the Invoices Sent and Responses to Same
#username = usernames['invoices']
#password = passwords['invoices']
#username = usernames['invo']
#password = passwords['invo']

for ix, username in enumerate(username_list):
    password = password_list[ix]
    box = boxlist[ix]
    imap = imaplib.IMAP4_SSL(imap_url)
    imap.login(username, password)
    #status, messages = imap.select('INBOX')
    print(f'Using username {username} and box {box}')
    status, messages = imap.select(box)
    # total number of emails
    messages = int(messages[0])
    print(f'Total number of messages in the invoices inbox is {messages}')

    # Get all orders from the last 30 days:
    dat90 = today - timedelta(360)
    odata = Orders.query.filter((Orders.Istat>2) & (Orders.Istat<5) & (Orders.Date3>dat90)).order_by(Orders.Date3).all()
    customer_set = []
    for odat in odata:
        #Find emails by subject and add to ardata database
        customer = odat.Shipper
        container = odat.Container
        customer_set.append(customer)
        sdat= SumInv.query.filter(SumInv.Container == container).first()
        if sdat is not None:
            summary = sdat.Si
        else:
            summary = None
        get_invoice_emails(container, summary, box)

    cus = set(customer_set)
    customer_set = list(cus)
    # Now look for and add emails sent as reminders or open balance reports
    print(f'Now getting reminders sent for customers in {customer_set}')
    for customer in customer_set:
        get_reminder_emails(customer, box)

    # close the connection and logout
    imap.close()
    imap.logout()



if nt == 'remote': tunnel.stop()