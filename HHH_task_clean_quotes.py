import os
import sys
import socket
from utils import getpaths
from datetime import datetime, timedelta

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument default is oslm')
    scac = 'fela'

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
    from models8 import Interchange, Orders, Drivers, Pins, Drops, People, PortClosed, Quotes
    from CCC_system_setup import websites, usernames, passwords, addpath3, imap_url, scac, companydata, nt, fromdirbase
    from email_reports import emailtxt
    from cronfuncs import conmatch
else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

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

lookback = runat - timedelta(360)
lbdate = lookback.date()

qdata = Quotes.query.filter(Quotes.Date < lbdate).all()
for qdat in qdata:
    thisid = qdat.id
    print(f'Deleting quote {thisid} from {qdat.Date} for Subject: {qdat.Subject} and Location: {qdat.Location}')
    Quotes.query.filter(Quotes.id == thisid).delete()
    db.session.commit()



