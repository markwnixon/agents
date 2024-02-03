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
    from models8 import Interchange, Orders, Ardata, SumInv
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

killon = 0
odata = Orders.query.filter((Orders.Shipper == 'Global Business Link') & (Orders. Hstat == -1)).all()
for odat in odata:
    print(f'Want to delete booking {odat.Booking} from Date: {odat.Date3}')
    id = odat.id
    if killon: Orders.query.filter(Orders.id == id).delete()
    db.session.commit()




if nt == 'remote': tunnel.stop()