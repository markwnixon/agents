import os
import sys
import socket
from utils import getpaths
import paramiko

import openpyxl
from openpyxl.styles import PatternFill, Border, Side, Alignment, Protection, Font, Color
from openpyxl.utils import get_column_letter
from utils import d2s, stripper, hasinput
import datetime
from datetime import timedelta


today = datetime.datetime.today()
today_str = today.strftime("%m/%d/%Y")
d = today.strftime("%B %d, %Y")
cutoff = datetime.datetime.now() - timedelta(365)
cutoff = cutoff.date()
over30 = datetime.datetime.now() - timedelta(30)
over30 = over30.date()
todaydate = today.date()

#Handle the input arguments from script file
try:
    scac = sys.argv[1]
except:
    print('Must have at least one argument...FELA or OSLM or NEVO')
    scac = 'OSLM'
try:
    nt = sys.argv[2]
except:
    print("No local/remote options provided, default is remote")
    nt = 'remote'

scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':

    print(f'Running FFF_Clean for {scac}')
    host_name = socket.gethostname()
    print("Host Name:", host_name)
    dropbox_path = getpaths(host_name, 'dropbox')
    ar_path = f'{dropbox_path}/Dray/{scac}_AR_Report.xlsx'
    sys_path = getpaths(host_name, 'system')
    sys.path.append(sys_path) #So we can import CCC_system_setup from full path

    os.environ['SCAC'] = scac
    os.environ['PURPOSE'] = 'script'
    os.environ['MACHINE'] = host_name
    os.environ['TUNNEL'] = nt
    delete_on = 1
    lame_delete = 1

    from remote_db_connect import db
    if nt == 'remote': from remote_db_connect import tunnel
    from models8 import Orders, Interchange, Invoices, Openi

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

def getfiles(nt, dir, ssh):
    if nt == 'local':
        file_list = os.listdir(dir)
    if nt == 'remote':
        command = f'ls -a {dir}'
        stdin, stdout, stderr = ssh.exec_command(command)
        file_list = stdout.read().decode().splitlines()
    return file_list

def delfiles(nt, dir, file, ssh):
    if nt == 'local':
        print(f'Deleting local file {file}')
        os.remove(f'{dir}/{file}')
    if nt == 'remote':
        print(f'Deleting remote file {file}')
        command = f'rm {dir}/{file}'
        stdin, stdout, stderr = ssh.exec_command(command)
        print(stdout.read().decode())

if scac != 'nogo':
    from CCC_system_setup import addpath

    if nt == 'remote':
        from CCC_system_setup import tup, dbp
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(tup[0],22, tup[1], tup[2])
        dirbase = f'{scac.lower()}/webapp/static/{scac}/data'
    else:
        ssh=None
        dirbase = addpath(f'static/{scac}/data')

    dir = f'{dirbase}/temp'
    file_list = getfiles(nt, dir, ssh)
    for file in file_list: delfiles(nt, dir, file, ssh)

    inv_dir = f'{dirbase}/vInvoice'
    prf_dir = f'{dirbase}/vProof'
    pkg_dir = f'{dirbase}/vPackage'
    man_dir = f'{dirbase}/vManifest'

    inv_file_list = getfiles(nt, inv_dir, ssh)
    prf_file_list = getfiles(nt, prf_dir, ssh)
    pkg_file_list = getfiles(nt, pkg_dir, ssh)
    man_file_list = getfiles(nt, man_dir, ssh)

    odata = Orders.query.all()
    for odat in odata:
        invname = odat.Invoice
        prfname = odat.Proof
        pkgname = odat.Package
        manname = odat.Manifest
        ojo = odat.Jo

        # Slim the invoices

        for file in inv_file_list:
            pre = file[0:2]
            if pre == 'IN':
                jo = file[3:11]
            elif pre == 'SI':
                jo = file[2:8]
            else:
                jo = None
            if jo == ojo:
                if file != invname:
                    print(f'Deleting invoice file {file}')
                    if delete_on: delfiles(nt, inv_dir, file, ssh)

        for file in pkg_file_list:
            ext = os.path.splitext(file)[1]
            lfile = len(file)
            if ext != '.pdf' and file != '.' and file != '..':
                print(f'Deleting file with bad extension: {file}')
                if lame_delete:
                    delfiles(nt, pkg_dir, file, ssh)
                    pkg_file_list = getfiles(nt, pkg_dir, ssh)
            elif lfile < 12 and file != '.' and file != '..':
                print(f'Deleting file with bad length: {file} {lfile}')
                if lame_delete:
                    delfiles(nt, pkg_dir, file, ssh)
                    pkg_file_list = getfiles(nt, pkg_dir, ssh)
            elif file != '.' and file != '..':
                body = os.path.splitext(file)[0]
                remain = body.split('_')
                try:
                    jo = remain[2]
                except:
                    print(f'No second remainder in {body}')
                if jo == ojo:
                    if file != pkgname:
                        print(f'Deleting package file {file} for jo {jo}')
                        if delete_on: delfiles(nt, pkg_dir, file, ssh)

        for file in man_file_list:
            ext = os.path.splitext(file)[1]
            lfile = len(file)
            if ext != '.pdf'and file != '.' and file != '..':
                print(f'Deleting file with bad extension: {file}')
                if lame_delete:
                    delfiles(nt, man_dir, file, ssh)
                    man_file_list = getfiles(nt, man_dir, ssh)
            elif lfile < 12 and file != '.' and file != '..':
                print(f'Deleting file with bad length: {file} {lfile}')
                if lame_delete:
                    delfiles(nt, man_dir, file, ssh)
                    man_file_list = getfiles(nt, man_dir, ssh)
            else:
                jo = file[8:16]
                if jo == ojo:
                    if file != manname:
                        print(f'Deleting manifest file {file} for jo {jo}')
                        if delete_on: delfiles(nt, man_dir, file, ssh)

        for file in prf_file_list:
            ext = os.path.splitext(file)[1]
            if ext != '.pdf' and file != '.' and file != '..':
                print(f'Deleting file with bad extension: {file}')
                if lame_delete:
                    delfiles(nt, prf_dir, file, ssh)
                    prf_file_list = getfiles(nt, prf_dir, ssh)
            else:
                if file[0:2] != 'Pr' and file != '.' and file != '..':
                    print(f'Deleting file with arbitrary name: {file}')
                    if lame_delete:
                        delfiles(nt, prf_dir, file, ssh)
                        prf_file_list = getfiles(nt, prf_dir, ssh)
                else:
                    if file[0:8] == 'Proof_Jo':
                        jo = file[9:17]
                        #print(f'Old version file {file} with jo {jo}')

                    elif file[0:5] == 'Proof':
                        jo = file[6:14]
                        #print(f'New version file {file} with jo {jo}')

                    if jo == ojo:
                        if file != prfname:
                            print(f'Deleting extra proof file {file}')
                            if delete_on: delfiles(nt, prf_dir, file, ssh)

if nt == 'remote':  tunnel.stop()