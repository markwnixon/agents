import os
import sys
import socket
from utils import getpaths

from utils import d2s, stripper, hasinput
import datetime
from datetime import timedelta
import calendar


today = datetime.datetime.today()
today_str = today.strftime("%m/%d/%Y")
d = today.strftime("%B %d, %Y")
#Calc days back desered to go back to last date of year two years prior
tyear = today.year - 2
last_day_back = datetime.date(tyear, 1, 1)
daysback = today.date() - last_day_back
days_far_back = daysback.days
cutoff = datetime.datetime.now() - timedelta(days_far_back)
cutoff = cutoff.date()
over30 = datetime.datetime.now() - timedelta(30)
over30 = over30.date()
todaydate = today.date()
thisyear = today.year
current_datetime = datetime.datetime.now()
local_time_of_day = current_datetime.strftime("%H:%M:%S")

exclude_these = ['FEL Ocean Div', 'First Eagle Logistics', 'One Stop Logistics', 'Nello Enterprise LLC', 'Jays Auto Service']


#Handle the input arguments from script file
try:
    scac = sys.argv[1]
    nt = 'remote'
except:
    print('Must have at least one argument...FELA or OSLM or NEVO')
    scac = 'FELA'
    nt = 'remote'

scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':

    print(f'Running FFF_dray_ARcheck for {scac}')
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
    from models8 import Orders, Interchange, Invoices, Openi, Income

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()

if scac != 'nogo':

    def get_last_day_of_month(date):
        _, last_day = calendar.monthrange(date.year, date.month)
        return datetime.datetime(date.year, date.month, last_day)

    def get_last_12_months():
        today = datetime.datetime.now()
        first_day_of_month = today.replace(day=1)
        first_day_of_month = first_day_of_month.date()
        last_day_of_month = get_last_day_of_month(first_day_of_month)
        last_day_of_month = last_day_of_month.date()
        last_12_months = []

        pback = int(days_far_back/30)
        print(f'Going back {pback} periods')
        for i in range(pback):
            # Calculate the first day of the current month
            last_12_months.append([first_day_of_month,last_day_of_month])
            # Calculate the last day of the previous month
            last_day_of_month = first_day_of_month - timedelta(days=1)
            first_day_of_month = last_day_of_month.replace(day=1)

        return last_12_months

    def get_all_periods(firstdate):
        year_periods = []
        daystogo = todaydate - firstdate
        daystogo = daystogo.days
        num_periods = int(daystogo/14) + 1
        first_day_of_period = firstdate
        last_day_of_period = firstdate + timedelta(days=13)
        for ix in range(num_periods):
            year_periods.append([first_day_of_period, last_day_of_period])
            first_day_of_period = first_day_of_period + timedelta(days=14)
            last_day_of_period = first_day_of_period + timedelta(days=13)

        #print(f'{year_periods}')

        return year_periods

    def calc_biweekly_income(sorter):

        #Calculate all biweekly period starting from 1/1/2023 (Saturday to Sunday)
        firstdate = datetime.date(2023, 1, 1)
        all_periods = get_all_periods(firstdate)

        for period in all_periods:
            d1 = period[0]
            d2 = period[1]
            # print(f'Income in Range of {d1} to {d2}')
            if sorter == 'returned':
                idata = Orders.query.filter((Orders.Istat>0) & (Orders.InvoDate >= d1) & (Orders.Date3 <= d2)).all()
                type = 'BR'
                desc = f'Biweely Income for Period {d1} to {d2} based on date container returned'
            elif sorter == 'invoiced':
                idata = Orders.query.filter((Orders.Istat > 0) & (Orders.InvoDate >= d1) & (Orders.InvoDate <= d2)).all()
                type = 'BI'
                desc = f'Biweely Income for Period {d1} to {d2} based on date invoiced'
            dtot = 0.00
            for idat in idata:
                # print(f'Order {idat.Jo} has ${idat.InvoTotal} from date: {idat.InvoDate}')
                try:
                    amt = float(idat.InvoTotal)
                    dtot += amt
                except:
                    amt = 0.00
                    print(f'Failed on getting an Amount for InvoTotal for job {idat.Jo}')
            #print(f'Invoice Total from {d1} to {d2} is ${dtot}')
            periodname = f'{d1} to  {d2}'

            input = Income(Period=periodname, Mrev=int(dtot*100), Mpaid=None, O120=None, O90=None, O60=None, O30=None, U30=None, Open=None, Description=desc, Type=type)
            db.session.add(input)

        db.session.commit()

        return


    # Calculate and report the monthly income from invoices:
    def calc_monthly_income(sorter):
        custlist = []


        todaydate = today.date()


        tot = 0.00
        tpaid = 0.00
        t120 = 0.00
        t90 = 0.00
        t60 = 0.00
        t30 = 0.00
        tu30 = 0.00
        topen = 0.00
        thisyear = todaydate.year

        # Get the last 12 months and years
        last_12_months = get_last_12_months()
        for month in last_12_months:
            d1 = month[0]
            d2 = month[1]
            #print(f'Income in Range of {d1} to {d2}')
            if sorter == 'invoiced':
                idata = Orders.query.filter((Orders.Istat>0) & (Orders.InvoDate >= d1) & (Orders.InvoDate <= d2)).all()
                type = 'MI'
                desc = f'Updated on {todaydate} at {local_time_of_day} based on Date Invoiced'
            elif sorter == 'returned':
                idata = Orders.query.filter((Orders.Istat > 0) & (Orders.Date3 >= d1) & (Orders.Date3 <= d2)).all()
                type = 'MR'
                desc = f'Updated on {todaydate} at {local_time_of_day} based on Date Container Returned'
            dtot = 0.00
            d30 = 0.00
            d60 = 0.00
            d90 = 0.00
            d120 = 0.00
            dpaid = 0.00
            dspecial = 0.00
            u30 = 0.00
            this_period_year = d1.year
            for idat in idata:
                #print(f'Order {idat.Jo} has ${idat.InvoTotal} from date: {idat.InvoDate}')
                if sorter == 'invoiced': datefor = idat.InvoDate
                elif sorter == 'returned': datefor = idat.Date3
                if datefor is not None:
                    try:
                        amt = float(idat.InvoTotal)
                        dtot += amt
                    except:
                        amt = 0.00
                        print(f'Failed on getting an Amount for InvoTotal for job {idat.Jo}')
                    istat = idat.Istat
                    special = idat.Seal
                    if istat == 5 or istat == 8:
                        dpaid += amt
                    elif special == 'Uncollectable':
                        dspecial += amt
                    else:
                        dover = today.date() - datefor
                        dover = dover.days
                        custlist.append(idat.Shipper)
                        if dover >= 120:
                            d120 += amt
                        elif dover >= 90:
                            d90 += amt
                        elif dover >= 60:
                            d60 += amt
                        elif dover >= 30:
                            d30 += amt
                        else:
                            u30 += amt
            dopen = dtot - dpaid - dspecial
            monthno = d1.month
            monthname = calendar.month_name[monthno]
            my = f'{monthname} {d1.year}'

            if thisyear != this_period_year:
                input = Income(Period=f'TOTAL for {thisyear}', Mrev=int(tot * 100), Mpaid=int(tpaid * 100), O120=int(t120 * 100),
                               O90=int(t90 * 100), O60=int(t60 * 100), O30=int(t30 * 100), U30=int(tu30 * 100),
                               Open=int(topen * 100), Description=desc, Type=type)
                db.session.add(input)
                tot = 0.00
                tpaid = 0.00
                t120 = 0.00
                t90 = 0.00
                t60 = 0.00
                t30 = 0.00
                tu30 = 0.00
                topen = 0.00
                thisyear = this_period_year

            input = Income(Period=my, Mrev=int(dtot*100), Mpaid=int(dpaid*100), O120=int(d120*100), O90=int(d90*100), O60=int(d60*100), O30=int(d30*100), U30=int(u30*100), Open=int(dopen*100), Description=desc, Type=type)
            db.session.add(input)


            tot += dtot
            tpaid += dpaid
            t120 += d120
            t90 += d90
            t60 += d60
            t30 += d30
            tu30 += u30
            topen += dopen

        input = Income(Period=f'TOTAL for {thisyear}', Mrev=int(tot * 100), Mpaid=int(tpaid * 100), O120=int(t120 * 100),
                      O90=int(t90 * 100), O60=int(t60 * 100), O30=int(t30 * 100), U30=int(t30 * 100),
                      Open=int(topen * 100), Description=desc, Type=type)
        db.session.add(input)
        db.session.commit()

        custset = set(custlist)
        return list(custset)



    def calc_company_open(custlist):
        desc = f'Report last updated on {todaydate} at {local_time_of_day} based on Date Invoiced'
        #Kill all then entries and add them each in
        Openi.query.delete()
        db.session.commit()

        tot = 0.00
        tpaid = 0.00
        t120 = 0.00
        t90 = 0.00
        t60 = 0.00
        t30 = 0.00
        tu30 = 0.00
        topen = 0.00

        for cust in custlist:
            if cust not in exclude_these:
                idata = Orders.query.filter((Orders.Shipper == cust) & (Orders.Istat > 0)  & (Orders.InvoDate > cutoff)).all()
                dtot = 0.00
                d30 = 0.00
                d60 = 0.00
                d90 = 0.00
                d120 = 0.00
                dpaid = 0.00
                u30 = 0.00
                for idat in idata:
                    try:
                        amt = float(idat.InvoTotal)
                        dtot += amt
                    except:
                        amt = 0.00
                    istat = idat.Istat
                    if istat == 5 or istat == 8:
                        dpaid += amt
                    else:
                        dover = today.date() - idat.InvoDate
                        dover = dover.days
                        if dover >= 120:
                            d120 += amt
                        elif dover >= 90:
                            d90 += amt
                        elif dover >= 60:
                            d60 += amt
                        elif dover >= 30:
                            d30 += amt
                        else:
                            u30 += amt
                dopen = dtot - dpaid
                input = Openi(Company=idat.Shipper, Mrev=int(dtot*100), Mpaid=int(dpaid*100), O120=int(d120*100), O90=int(d90*100), O60=int(d60*100), O30=int(d30*100), U30=int(u30*100), Open=int(dopen*100), Description=desc)
                db.session.add(input)
                tot += dtot
                tpaid += dpaid
                t120 += d120
                t90 += d90
                t60 += d60
                t30 += d30
                tu30 += u30
                topen += dopen
        input = Openi(Company='TOTAL', Mrev=int(tot * 100), Mpaid=int(tpaid * 100), O120=int(t120 * 100),
                      O90=int(t90 * 100), O60=int(t60 * 100), O30=int(t30 * 100), U30=int(t30 * 100),
                      Open=int(topen * 100), Description=desc)
        db.session.add(input)
        db.session.commit()


    success = 0
    trys = 0
    while success == 0 and trys < 20:
        try:
            odata = Orders.query.filter((Orders.Istat > 0) & (Orders.Date3 > cutoff)).all()
            success = 1
        except:
            print(f'Could not open tunnel on try {trys}')
            trys = trys + 1

    if success == 1:
        badjo = []
        for odat in odata:
            invodate = odat.InvoDate
            invototal = odat.InvoTotal
            jo = odat.Jo
            status = odat.Seal
            if invodate == None or invototal == None:
                print(f'Order {jo} is invoiced without complete invoice information: has invodate {invodate} and invototal: {invototal}')
                idat = Invoices.query.filter(Invoices.Jo == jo).first()
                if idat is not None:
                    total = f'{idat.Total}'
                    date = idat.Date
                    odat.InvoTotal = total
                    odat.InvoDate = date
                    db.session.commit()
                else:
                    status = odat.Seal
                    istat = odat.Istat
                    if istat > 0 and istat < 5:
                        print(f'Order {jo} is recorded as invoiced but has no invoice')
                    if status == 'Uncollectable':
                        print(f'Order {jo} is marked as uncollectable')
                    badjo.append(jo)



        #odata = Orders.query.filter((Orders.Istat > 0) & (Orders.InvoDate > cutoff)).all()
        #Now grab by the Invoice Date:

        #Remove the old data in the income table start fresh each time
        Income.query.delete()
        db.session.commit()



        custlist = calc_monthly_income('invoiced')
        #print(custlist)
        calc_company_open(custlist)

        nolist = calc_monthly_income('returned')

        calc_biweekly_income('returned')
        #This gets the bi-weekly income by date container returned

        calc_biweekly_income('invoiced')
        #This gets the bi-weekly income by date container returned

        quit()



if nt == 'remote': tunnel.stop()