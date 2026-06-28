import os
import sys
import socket
from utils import getpaths, hasinput, d2s, stripper

scac = 'NEVO'
SCAC = scac.upper()
nt = 'remote'

print(f'Running Payments Creator for {scac}')
host_name = socket.gethostname()
print("Host Name:", host_name)
dropbox_path = getpaths(host_name, 'dropbox')
ar_path = f'{dropbox_path}/Dray/{scac}_AR_Report.xlsx'
sys_path = getpaths(host_name, 'system')
sys.path.append(sys_path)  # So we can import CCC_system_setup from full path

os.environ['SCAC'] = scac
os.environ['PURPOSE'] = 'script'
os.environ['MACHINE'] = host_name
os.environ['TUNNEL'] = nt


from remote_db_connect import tunnel, db
from models8 import Gledger, PaymentsRec, Orders

import datetime
from datetime import timedelta
year, ytd_month, ytd_day = 2023, 1, 1
today = datetime.date(year, ytd_month, ytd_day)
todayyear = today.year
nextyear = year+1

idcomp = []

gdata = Gledger.query.filter((Gledger.Date >= today) & ((Gledger.Type == 'ID') | (Gledger.Type == 'DD')) ).all()
for gdat in gdata:
    thisid = gdat.id
    jo = gdat.Tcode
    daterec = gdat.Date
    ref = gdat.Ref
    type = gdat.Type
    source = gdat.Source
    acct = gdat.Account
    if thisid not in idcomp:
        gsubdata = Gledger.query.filter( (Gledger.Type == type) & (Gledger.Ref == ref) & (Gledger.Source == source) & (Gledger.Date == daterec)).all()
        amttot = 0.00
        jolist = []
        for gsub in gsubdata:
            nid = gsub.id
            amt = float(gsub.Debit)/100
            amttot += amt
            idcomp.append(nid)
            jolist.append(gsub.Tcode)
            print(f'Summing up payment for JO:{gsub.Tcode} Date: {gsub.Date} Amount: {amt} Account: {gsub.Account} Source: {gsub.Source} Ref: {gsub.Ref}')
        payamt = int(amttot*100)
        print(f'****Ths final payment input is: Amount: {payamt} Account: {acct}, Source: {source}, Type: {type}, Com: {gdat.Com} Recorded: {gdat.Recorded} Date: {daterec}, Ref: {ref}******')
        input_paymnt = PaymentsRec(Amount=payamt, Account=acct, Source=source, Type=type, Com=gdat.Com, Recorded=gdat.Recorded, Date=daterec, Ref=ref)
        db.session.add(input_paymnt)
        db.session.commit()
        refid = input_paymnt.id  # this links the total payment to the applied payment for the job
        for gsub in gsubdata:
            gsub.Sid = refid
        for njo in jolist:
            odat = Orders.query.filter(Orders.Jo == njo).first()
            if odat is not None:
                odat.QBi = refid
        db.session.commit()
