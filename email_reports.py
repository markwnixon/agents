import smtplib
import mimetypes
from email.mime.multipart import MIMEMultipart
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
import ntpath
import shutil
import os    
import numpy as np
import subprocess
import fnmatch
from collections import Counter
import datetime
from PyPDF2 import PdfFileReader

from CCC_system_setup import usernames, passwords, websites, companydata

def emailshipreport(tabdata):
    
    #newfile= ntpath.basename(mfile)
    #shutil.copy(mfile,newfile)

    emailfrom = usernames['mnix']
    emailto = usernames['info']
    emailcc = usernames['expo']
    #fileToSend = tfile
    username = usernames['mnix']
    password = passwords['mnix']

    msg = MIMEMultipart()
    msg["From"] = emailfrom
    msg["To"] = emailto
    msg["Cc"] = emailcc
    msg["Subject"] = 'Ship Report'

    s1='<td>'
    s2='</td><td>'
    body = '<html><body><p>Here is status of FEL related Shipline Activity</p><p>Blue = arrived, Red = arrives in less than 10 days, Ordered by new arrival date</p>\n\n'
    body = body + "<table cellspacing='20'><tr>"
    body = body + "<td style='text-align:center'><b>Days<br>Away</b></td><td style='text-align:center'><b>Status</b></td><td style='text-align:center'><b>New<br>Arrival<br>Date</b></td><td style='text-align:center'><b>Release</b></td><td style='text-align:center'><b>Old<br>Arrival<br>Date</b></td><td style='text-align:center'><b>Booking</b></td><td style='text-align:center'><b>Container</b></td><td style='text-align:center'><b>Bill<br>To</b></td><td style='text-align:center'><b>Exporter</b></td></tr>\n"
    for tab in tabdata:
        try:
            daway=int(tab[0])
            if daway<0:
                s1="<td style='text-align:center;color: blue'>"
                s2='</td>'+s1
            elif daway<11:
                s1="<td style='text-align:center;color: red'>"
                s2='</td>'+s1
            else:
                s1="<td style='text-align:center'>"
                s2='</td>'+s1
                
        except:
            err=1
                
        body=body+'<tr>'+s1+tab[0]+s2+tab[1]+s2+tab[2]+s2+tab[3]+s2+tab[4]+s2+tab[5]+s2+tab[6]+s2+tab[8]+s2+tab[9]+'</td></tr>\n'
   
    body=body+'</table></body></html>'
    msg.attach(MIMEText(body, 'html'))

    #attachment = open(fileToSend, "rb")
 
    #part = MIMEBase('application', 'octet-stream')
    #part.set_payload((attachment).read())
    #encoders.encode_base64(part)
    #part.add_header('Content-Disposition', "attachment; filename= %s" % fileToSend)
 
    #msg.attach(part)
    
    server = smtplib.SMTP(websites['mailserver'])
    #server.starttls()
    server.login(username,password)
    emailto = [emailto, emailcc]
    server.sendmail(emailfrom, emailto, msg.as_string())
    server.quit()

def emailtxt(title, text):
    ourserver = websites['mailserver']

    emailfrom = usernames['info']
    emailto = usernames['mnix']

    # fileToSend = tfile
    username = usernames['info']
    password = passwords['info']

    msg = MIMEMultipart()
    msg["From"] = emailfrom
    msg["To"] = emailto
    msg["Subject"] = title

    body = '<html><body><p>Here is cron run report:</p>\n\n'
    body = body + text
    body = body + '</table></body></html>'
    msg.attach(MIMEText(body, 'html'))

    # attachment = open(fileToSend, "rb")

    # part = MIMEBase('application', 'octet-stream')
    # part.set_payload((attachment).read())
    # encoders.encode_base64(part)
    # part.add_header('Content-Disposition', "attachment; filename= %s" % fileToSend)

    # msg.attach(part)
    print(ourserver, username, password)
    server = smtplib.SMTP(ourserver)
    server.starttls()
    code, check = server.login(username, password)
    print('check', code, check.decode("utf-8"))
    emailto = [emailto]
    server.sendmail(emailfrom, emailto, msg.as_string())
    server.quit()
    
def aplinvoice(mfile,mtext,mdate,invoco,sendto):

    fileToSend = ntpath.basename(mfile)
    shutil.copy(mfile,fileToSend)
    print(f'file to send is:{fileToSend}')

    if invoco == 'apl' and sendto == 'aplnow':
        emailfrom = usernames['mnix']
        #emailto = 'gfckl.apl.ap.america.trucking@apl.com'
        emailto = 'nash.edi.upload@apl.com'
        #emailto = 'markwnixon@gmail.com'
        emailcc = usernames['info']
    elif invoco == 'cma' and sendto == 'cmanow':
        emailfrom = usernames['mnix']
        emailto = 'ssc.usaapinvoices@cma-cgm.com'
        #emailto = 'markwnixon@gmail.com'
        emailcc = usernames['info']
    else:
        emailfrom = usernames['mnix']
        emailto = usernames['mnix']
        emailcc = usernames['expo']

    # fileToSend = tfile
    username = usernames['mnix']
    password = passwords['mnix']

    msg = MIMEMultipart()
    msg["From"] = emailfrom
    msg["To"] = emailto
    msg["Cc"] = emailcc
    if invoco == 'apl':
        msg["Subject"] = f'Account Payable Dept - SSINV to EDI -- First Eagle Logistics {mdate}'
        body = 'APL LARA Spreadsheet is Attached.' + mtext
    if invoco == 'cma':
        msg["Subject"] = f'Account Payable Dept CMA CMG - SSINV to EDI from First Eagle Logistics {mdate}'
        body = 'CMA LARA Spreadsheet is Attached.' + mtext

    cdata = companydata()
    body = body + f'<br>_________________<br>{cdata[2]}<br>{cdata[5]}<br>{cdata[6]}<br>{cdata[7]}'

    msg.attach(MIMEText(body, 'html'))

    attachment = open(fileToSend, "rb")

    part = MIMEBase('application', 'octet-stream')
    part.set_payload((attachment).read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename= "{fileToSend}"')
    msg.attach(part)

    print(ourserver, username, password)
    server = smtplib.SMTP(ourserver)
    server.starttls()
    code, check = server.login(username, password)
    print('check', code, check.decode("utf-8"))
    emailto = [emailto, emailcc]
    server.sendmail(emailfrom, emailto, msg.as_string())
    server.quit()
    