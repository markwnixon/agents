import os
import sys
import socket
from utils import getpaths
from requests import get



import openpyxl
from openpyxl.styles import PatternFill, Border, Side, Alignment, Protection, Font, Color
from openpyxl.utils import get_column_letter
from utils import d2s, stripper, hasinput
import datetime
from datetime import timedelta


today = datetime.datetime.today()
today_str = today.strftime("%m/%d/%Y")
d = today.strftime("%B %d, %Y")
cutoff = datetime.datetime.now() - timedelta(30)
cutoff = cutoff.date()
over30 = datetime.datetime.now() - timedelta(30)
over30 = over30.date()
todaydate = today.date()

scac = 'NEVO'
nt = 'remote'
scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':

    print(f'Running FFF_Linwood for SCAC: {scac}')
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

    from CCC_system_setup import apikeys
    API_KEY_GEO = apikeys['gkey']
    API_KEY_DIS = apikeys['dkey']


    def get_address_details(address):
        #print(address)
        address = address.replace('\n', ' ').replace('\r', '')
        address = address.replace('#', '')
        address = address.strip()
        address = address.replace(" ", "+")
        url = f'https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={API_KEY_GEO}'
        response = get(url)
        data = address_resolver(response.json())
        data['address'] = address
        backupcity = 'None'
        # lat = data['latitude']
        # lon = data['longitude']
        # print(lat,lon)
        return data, backupcity


    def address_resolver(json):
        final = {}
        if json['results']:
            data = json['results'][0]
            for item in data['address_components']:
                #print(f'address resolver item {item}')
                for category in item['types']:
                    data[category] = {}
                    data[category] = item['long_name']
            final['street'] = data.get("route", None)
            final['state'] = data.get("administrative_area_level_1", None)
            final['city'] = data.get("locality", None)
            final['county'] = data.get("administrative_area_level_2", None)
            final['country'] = data.get("country", None)
            final['postal_code'] = data.get("postal_code", None)
            final['neighborhood'] = data.get("neighborhood", None)
            final['sublocality'] = data.get("sublocality", None)
            final['housenumber'] = data.get("housenumber", None)
            final['postal_town'] = data.get("postal_town", None)
            final['subpremise'] = data.get("subpremise", None)
            final['latitude'] = data.get("geometry", {}).get("location", {}).get("lat", None)
            final['longitude'] = data.get("geometry", {}).get("location", {}).get("lng", None)
            final['location_type'] = data.get("geometry", {}).get("location_type", None)
            final['postal_code_suffix'] = data.get("postal_code_suffix", None)
            final['street_number'] = data.get('street_number', None)
        return final

    from remote_db_connect import db
    if nt == 'remote': from remote_db_connect import tunnel
    from models8 import Orders, Interchange, Invoices, Openi

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

datasort = []
if scac != 'nogo':
    idata = Interchange.query.filter( ((Interchange.TruckNumber=='0494F2') | (Interchange.TruckNumber=='39920F')) &(Interchange.Type.contains('Out')) & (Interchange.Date>over30)).all()
    for idat in idata:
        jo = idat.Jo
        com = idat.Company
        invdat = Invoices.query.filter(Invoices.Jo == jo).all()
        if invdat is not None:
            nonchass = 0.00
            for inv in invdat:
                if inv.Service != 'Chassis Fees':
                    nonchass = nonchass + float(inv.Amount)

        odat = Orders.query.filter(Orders.Jo == jo).first()
        if odat is not None:
            address = odat.Dropblock2
            adata, backup = get_address_details(address)
            #print(adata)
            #print(f'City backup: {backup}')
            try:
                city = adata['city']
            except:
                city = backup

        # Not complete until returned
        idat2 = Interchange.query.filter( (Interchange.Jo==jo)&(Interchange.Type.contains('In')) ).first()
        if idat2 is not None:
            Date2 = idat2.Date
        else:
            if nonchass>0: Date2 = 'Depot Return'
            else: Date2 = 'Not Returned'
        #print(idat.Driver, idat.Container, idat.Date, idat.Time)
        datasort.append([idat.Driver, idat.Jo, idat.Container, idat.Date, idat.Time, nonchass, Date2, com, city])
    sorted_matrix = sorted(datasort, key=lambda x: (x[3], x[4]))
    for sorted in sorted_matrix:
        print(f'{sorted[1]}\t{sorted[2]}\t{sorted[3]}\t{sorted[4]}\t{sorted[5]}\t{sorted[6]}\t{sorted[7]}\t{sorted[8]}')


tunnel.stop()
