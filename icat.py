import os
import sys
import socket
from utils import getpaths, hasinput, d2s, stripper

scac = 'FELA'
SCAC = scac.upper()
nt = 'remote'

print(f'Running ICAT reader {scac}')
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
from models8 import Interchange, Orders, Invoices

import datetime
import openpyxl
import shutil, sys
from utils import d2f, d2s
import pandas as pd
from pandas import ExcelWriter
from pandas import ExcelFile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

import numpy as np
import math
import subprocess

from PIL import Image

from PyPDF2 import PdfReader, PdfWriter, PdfMerger

import datetime
from datetime import timedelta

from email_reports import aplinvoice

today = datetime.datetime.today()
today_str = today.strftime("%m/%d/%Y")
d = today.strftime("%B %d, %Y")
print(today)
cutoff = datetime.datetime.now() - timedelta(120)
cutoff = cutoff.date()

def simplemerge(infile, backfile, outfile):
    reader = PdfReader(open(infile, 'rb'))
    first_page = reader.pages[0]
    sup_reader = PdfReader(open(backfile, 'rb'))
    sup_page = sup_reader.pages[0]  # This is the selected page, can pick any page of document
    sup_page.merge_page(first_page)
    writer = PdfWriter()
    writer.add_page(sup_page)
    with open(outfile, 'wb') as f:
        writer.write(f)
    f.close()

def pdfadd(infile, outfile):
    #check to see if outfile exists
    merger = PdfMerger()
    try:
        merger.append(outfile)
    except:
        print(f'Outfile {outfile} does not exist so just using input file')
    merger.append(infile)
    outfile2 = path1 + f'icat_inspection_{last5}_temp.pdf'
    merger.write(outfile2)
    merger.close()
    shutil.move(outfile2,outfile)
    #Adds infile to outfile and saves as outfile
    #If outfile does not exist it is created

#Handle the input arguments from script file

try:
    arg1 = sys.argv[1]
except:
    print('Must have at least one argument...icat or towbol')
    arg1 = 'towbol'
if arg1 == 'icat' or arg1 == 'towbol':
    print(f'Running icat documenter for {arg1}')
    print('run icat.sh icat to create the inspection sheet')
    print('run icat.sh towbol to create the tow bol')
else:
    arg1 = 'nogo'

if arg1 != 'nogo':


    # Give the location of the file
    path1 = '/home/mark/Tow/'
    locrec = path1+'TowMain.xls'

    df = pd.read_excel(locrec, sheet_name='Tows')
    da = pd.read_excel(locrec, sheet_name='Addresses')
    dp = pd.read_excel(locrec, sheet_name='Locations')

    blankfile = None
    if arg1 == 'towbol':
        blankfile = path1 + 'towbolblank.pdf'
    if arg1 == 'icat':
        blankfile = path1 + 'ICATblank.pdf'

    datafile = path1 + 'temp.pdf'
    signer = path1 + 'mark1.png'


    def printaddress(thisitem,aloc):
        print(f'Looking for thisitem {thisitem} and aloc {aloc}')
        thisloc= da[da.Short == aloc]
        for i in range(1,5):
            pt = 'Addr' + str(i)
            thisadd = thisloc[pt].item()
            thispr= dp[(dp.Item == thisitem) & (dp.Subitem == pt)]
            x = int(thispr.X.item())
            y = int(thispr.Y.item())
            c.drawString(x, y, thisadd)

    def printitem(key,item):
        thispr = dp[dp.Item == key]
        x = int(thispr.X.item())
        y = int(thispr.Y.item())
        c.drawString(x, y, item)

    def checkval(input):
        if isinstance(input, str): return input
        elif math.isnan(input): return ''
        elif isinstance(input, float): return str(int(input))
        elif isinstance(input, int): return str(input)
        else: return input

    def get_drop(list,ix):
        ht1 = list[ix][1]
        try:
            ht2 = list[ix + 1][1]
            return max(ht1,ht2)
        except:
            return ht1

    if blankfile is not None:
        for i in df.index:
            c = canvas.Canvas(datafile, pagesize=letter)
            doit = df['Create'][i]
            if doit == 1:
                car = df['Vehicle'][i]
                vin = df['Vin'][i]
                last5 = vin[-5:]
                imagepath = path1 + f'{last5}/'
                if not os.path.isdir(imagepath): os.mkdir(imagepath)
                color = checkval(df['Color'][i])
                interior = df['Interior'][i]
                date1 = df['Date1'][i]
                date2 = df['LoadDate'][i]
                towco = df['TowCo'][i]
                pickup = df['Pickup'][i]
                delto = df['Delto'][i]
                order = checkval(df['Order'][i])
                booking = checkval(df['Booking'][i])
                container = checkval(df['Container'][i])
                size = checkval(df['Size'][i])
                seal = checkval(df['Seal'][i])
                miles = checkval(df['Miles'][i])
                newdate = date1.date()
                date1 = f'{newdate}'
                #print(f'On {date1} This car in frame {i} is {car} color {color} miles {miles} with vin {vin} and last5 {last5} and towco {towco} {pickup} {delto}')
                #odat = Orders.query.filter((Orders.Shipper.contains('ICAT')) & (Orders.Booking == booking) ).first()
                odat = None

                #From data above this section creates the ICAT tow BOL
                if arg1 == 'towbol':
                    print(f'towco is', towco)
                    c.setFont('Helvetica', 10, leading=None)
                    printaddress('towco',towco)
                    printaddress('pickup', pickup)
                    printaddress('delto', delto)
                    carline = f'{car} {color} VIN:{vin}   (Loading under ICAT #{order} Booking: {booking})'
                    printitem('Vehicle', carline)
                    printitem('Date1',date1)
                    driver = da[da.Short == towco].Poc.item()
                    printitem('Driver',driver)
                    outputfile = path1 + f'towbol_{last5}.pdf'
                    if odat is not None:
                        current = odat.Description
                        odat.Description = f'{current}\n{carline}\nPickup from {pickup}'
                        db.session.commit()

                #From data at top this section create the ICAT inspectiondictionary sheet
                if arg1 == 'icat':
                    c.setFont('Helvetica', 12, leading=None)
                    outputfile = path1 + f'icat_inspection_{last5}.pdf'
                    outputfile2 = path1 + f'{last5}/icat_inspection_{last5}.pdf'

                    year,make,model = car.split()
                    #print(year, make, model)
                    notes = f"ICAT#{order} Bk:{booking} Con:{container} {size}' Seal:{seal}"
                    print(f'Loading {year} {make} {model} {vin} {notes}')
                    printitem('Year', year)
                    printitem('Make', make)
                    printitem('Model', model)
                    printitem('Color', color)
                    printitem('Miles', miles)
                    printitem('Vin', vin)
                    printitem('Interior', interior)
                    printitem('Notes', notes)
                    newdate = date2.date()
                    date2 = f'{newdate}'
                    printitem('Date2', date2)
                    printitem('Received', 'Mark Nixon')
                    printitem('Init1', 'mwn')
                    printitem('Init2', 'mwn')
                    c.drawImage(signer, 150, 115, mask='auto')

                #Which ever document was created this merges the data onto the correct blank file
                c.showPage()
                c.save()
                simplemerge(datafile, blankfile, outputfile)

                #If creating the inspection sheet we will also create a pdf of the pictures in subdirectory
                if arg1 == 'icat':
                    try:
                        shutil.copy(outputfile, outputfile2)
                    except:
                        print(f'Could not copy icat inspection to subdirectory {last5}')
                    basewidth = 290
                    imlist = []
                    imagepath = path1 + f'{last5}/'
                    if not os.path.isdir(imagepath): os.mkdir(imagepath)

                    pictlist = os.listdir(imagepath)
                    newpictlist = [pict for pict in pictlist if '.pdf' not in pict]
                    pictlist = [pict for pict in newpictlist if 'a300' not in pict]
                    for ix, file in enumerate(newpictlist):
                        #print(file)
                        fpath = f'{imagepath}{file}'
                        img = Image.open(fpath)
                        wpercent = (basewidth / float(img.size[0]))
                        hsize = int((float(img.size[1]) * float(wpercent)))
                        img = img.resize((basewidth, hsize), Image.LANCZOS)
                        newfile = f'{imagepath}/a{ix}_{last5}.jpg'
                        img.save(newfile)
                        imlist.append([newfile,hsize])

                    #Now sort the list by height
                    imlist = sorted(imlist, key=lambda x: x[1])

                    outputfile = path1 + f'load_picts_{last5}.pdf'
                    outputfile2 = path1 + f'{last5}/load_picts_{last5}.pdf'
                    pictfile = path1 + f'load_working_{last5}.pdf'
                    #Need to delete the old outputfile if it exists or else it will be amended
                    try:
                        os.remove(outputfile)
                    except:
                        print('No outputfile exists')
                    c = canvas.Canvas(pictfile, pagesize=letter)
                    up = 770
                    for jx, imarray in enumerate(imlist):
                        im = imarray[0]
                        if (jx % 2) == 0:
                            right = 12
                            drop = get_drop(imlist,jx)
                            up = up - drop - 10
                            if up < 10:
                                c.showPage()
                                c.save()
                                pdfadd(pictfile, outputfile)
                                up = 770 - drop - 10
                                c = canvas.Canvas(pictfile, pagesize=letter)
                        else:
                            right = 308
                        c.drawImage(im, right, up, mask='auto')

                    c.showPage()
                    c.save()
                    pdfadd(pictfile, outputfile)
                    try:
                        os.remove(pictfile)
                    except:
                        print('Could not remove working file')
                    # Now move copies of the files over to the directoreis for permanant storage
                    try:
                        shutil.copy(outputfile,outputfile2)
                    except:
                        print('Could not copy to final location')
                    if odat is not None:
                        pcache = odat.Pcache
                        outputfile = path1 + f'icat_inspection_{last5}.pdf'
                        pfile=f'icat_inspection_{last5}_{pcache}.pdf'
                        odat.Proof = pfile
                        pcache = pcache + 1
                        odat.Pcache = pcache
                        db.session.commit()
                        subprocess.run(["scp", outputfile, f"mnixon@ssh.pythonanywhere.com:/home/mnixon/class8/tmp/FELA/data/vproofs/{pfile}"])
                try:
                    os.remove(datafile)
                except:
                    print('Could not remove working file')













