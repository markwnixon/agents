# This python file is run using the script ships.sh

import os
import sys

import socket
from utils import getpaths, d1s, d2s

import time
from datetime import datetime, timedelta

import requests
import json
from math import sqrt

#Handle the input arguments from script file
#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    nt = 'remote'
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    print('Setting SCAC to FELA since none provided')
    scac = 'nevo'
    nt = 'remote'

scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running GGG_Ship_Schedule for {scac} in tunnel mode: {nt}')

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

    from remote_db_connect import db
    if nt == 'remote': from remote_db_connect import tunnel
    from models8 import Ships, Exports, Imports, Orders
    from CCC_system_setup import websites, usernames, passwords

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()


printif = 0

runat = datetime.now()
tnow = runat.strftime("%M")
mins = int(tnow)
today = runat.date()
port_start = today - timedelta(days=14)
ps = port_start.strftime("%m/%d/%Y")
port_end = today + timedelta(days=45)
pe = port_end.strftime("%m/%d/%Y")
print(' ')
print('_______________________________________________________')
print(f'This sequence run date: {today}')
print(f'Port date range from: {ps} to {pe}')
print('_______________________________________________________')
print(' ')
textblock = f'This sequence run at {runat} and minutes are {mins}\n'

conyes = 0
contrys = 0
#print(f'Attempting to connect to database and table Imports....')
while contrys < 4 and conyes == 0:
    try:
        imports = Imports.query.filter(Imports.Active==1).all()
        conyes = 1
    except:
        print(f'Could not connect to database on try {contrys}')
        contrys += 1
    time.sleep(1)
#With a connection established to database continue
#select(distinct(YourModel.your_column))).scalars().all()
def prep_val(val):
    if val is None: return None
    else: return val.strip()

uships = []
unames = []
vships = []
vnames = []
if imports is not None:
    for imp in imports:
        vessel = imp.Vessel.strip()
        container = imp.Container
        confound = Orders.query.filter((Orders.Container == container) & (Orders.Hstat < 2)).first()
        if confound is None:
            vessel = 'NOF'
            imp.Active = 0
            db.session.commit()

        if vessel not in uships and vessel != 'NOF':
            voyage = imp.Voyage.strip()
            uships.append(vessel)
            unames.append(f'{vessel}={voyage}')

#print(f'Found {uships} unique and active Import Vessels')
#print(f'Found {unames} unique and active Import Vessels')
exports = Exports.query.filter(Exports.Active==1).all()
if exports is not None:
    for exp in exports:
        vessel = exp.Vessel
        if vessel is not None: vessel = vessel.strip()
        if vessel not in vships and vessel != 'NOF':
            try:
                voyage = exp.Voyage.strip()
            except:
                voyage = 'None'
            vships.append(vessel)
            vnames.append(f'{vessel}={voyage}')
#print(f'Found {vships} unique and active Export Vessels')
#print(f'Found {vnames} unique and active Export Vessels')
ship_names_unique = list(set(unames+vnames))
#print(f'Found {ship_names_unique} unique and active Combined Vessels')

# Start the api capture of ships...
def get_access_token(username, password, server):
    headers = {
        'Content-Type': 'application/json'
            }

    token_url = f'{server}/api/Auth/GetToken'
    payload = {
        'username': username,
        'password': password,
        'grant_type': 'password'
    }

    response = requests.post(token_url, data=json.dumps(payload), headers=headers)

    if response.status_code == 200:
        return response.json().get('token'), response.json().get('userName')
    else:
        raise Exception('Failed to get access token')

def get_vessel_schedule(server, headers, data):
    api_url = f'{server}/api/VesselSchedule/GetVesselSchedule'
    response = requests.get(api_url, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        # Print the response content (JSON format in this example)
        keyret = []
        valret = []
        #print(response.json())
        datas = response.json()
        for data in datas:
            keyret.append(list(data.keys()))
            valret.append(list(data.values()))
        return keyret, valret
    else:
        print(response.status_code)
        raise Exception(f'Failed to get data from {api_url}')




apigo = 1
if apigo:

    params = {
              "userName": "1Stop",
              "password": "xKZyMJnR"
              }
    server1 = 'https://tosserviceuat-api.portsamerica.com:9001'
    server2 = 'https://tosservice-api.portsamerica.com:9001'
    username = '1Stop'
    password = 'xKZyMJnR'

    access_token, access_username = get_access_token(username, password, server1)
    #print('Access Token:', access_token)
    #print('Access Username:', access_username)
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'SiteID':'SGT_BAL'
             }


    data = {
        "startDate": ps,
        "endDate": pe
    }
    keyret, valret = get_vessel_schedule(server2, headers, data)
    print('##########################################')
    print('Successful return of data from VesselSchedule/GetVesselSchedule:)')
    #keys = keyret[0]
    notthere = []
    shipfound = []
    for val in valret:
        vessel = prep_val(val[0])
        voyin = prep_val(val[2])
        voyout = prep_val(val[3])
        testin = f'{vessel}={voyin}'
        testout = f'{vessel}={voyout}'
        #print(f'Comparing {testin} to {ship_names_unique}')
        #print(f'Comparing {testout} to {ship_names_unique}')
        if testin in ship_names_unique: shipfound.append(testin)
        if testout in ship_names_unique: shipfound.append(testout)
    print(f'Ships found: {shipfound}')

    for ship_name in ship_names_unique:
        if ship_name not in shipfound:
            notthere.append(ship_name)
    print('Ships not found:', notthere)
    print('##########################################')

    #####
    # Section to update the Ship Database:
    for val in valret:
        vessel = prep_val(val[0])
        voyin = prep_val(val[2])
        voyout = prep_val(val[3])
        testin = f'{vessel}={voyin}'
        testout = f'{vessel}={voyout}'
        # Only address the vessels required
        if testin in shipfound or testout in shipfound:
            code = prep_val(val[1])
            voyin = prep_val(val[2])
            ssco = prep_val(val[5])
            estarrive = prep_val(val[6])
            estdepart = prep_val(val[7])
            gencut = prep_val(val[8])
            refcut = prep_val(val[9])
            hazcut = prep_val(val[10])
            actarrival = prep_val(val[11])
            actdepart = prep_val(val[12])
            update_comments = ''

            sdat = Ships.query.filter((Ships.Vessel == vessel) & (Ships.VoyageIn == voyin)).order_by(Ships.id.desc()).first()
            if sdat is None:
                print(f'Adding data for vessel {vessel} {voyin} {voyout} which is new to the schedule')
                # Then add the ship to the database
                input = Ships(Vessel=vessel, Code=code, Imports=0, VoyageIn=voyin, VoyageOut=voyout, SSCO=ssco, ActArrival=actarrival, GenCutoff=gencut, RefCutoff=refcut, HazCutoff=hazcut, EstArrival=estarrive, EstDeparture=estdepart, ActDeparture=actdepart, Update=1)
                db.session.add(input)
                db.session.commit()
            else:
            # Check to see if the data has changed

                if sdat.Vessel != vessel or sdat.VoyageIn != voyin or sdat.VoyageOut != voyout or sdat.GenCutoff != gencut or sdat.EstArrival != estarrive:
                    # Then add the ship to the database
                    if sdat.GenCutoff != gencut: update_comments = f'{update_comments} Cutoff has moved from {sdat.GenCutoff} to {gencut}'
                    if sdat.EstArrival != estarrive: update_comments = f'{update_comments} Ship arrival has moved from {sdat.EstArrival} to {estarrive}'
                    update = sdat.Update + 1
                    print(f'There are changes in the Vessel schedule that require updating for Vessel {sdat.Vessel}')
                    input = Ships(Vessel=vessel, Code=code, Imports=0, VoyageIn=voyin, VoyageOut=voyout, SSCO=ssco,
                                  ActArrival=actarrival, GenCutoff=gencut, RefCutoff=refcut, HazCutoff=hazcut,
                                  EstArrival=estarrive, EstDeparture=estdepart, ActDeparture=actdepart, Update=update)
                    db.session.add(input)
                    db.session.commit()
                    print(f'Vessel {vessel} already on the schedule but required these changes: {update_comments}')
                else:
                    print(f'Vessel {vessel} already on the schedule and no changes')

if nt == 'remote': tunnel.stop()
