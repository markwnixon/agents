import os
import sys
import socket
from utils import getpaths
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

host_name = socket.gethostname()
scac = 'FELA'
nt = 'remote'
print("Host Name:", host_name)
dropbox_path = getpaths(host_name, 'dropbox')
ar_path = f'{dropbox_path}/Dray/{scac}_AR_Report.xlsx'
sys_path = getpaths(host_name, 'system')
sys.path.append(sys_path)  # So we can import CCC_system_setup from full path


os.environ['SCAC'] = scac
os.environ['PURPOSE'] = 'script'
os.environ['MACHINE'] = host_name
os.environ['TUNNEL'] = nt

import sshtunnel


tup = ['ssh.pythonanywhere.com', 'nixonai', 'Birdie$10', 'nixonai.mysql.pythonanywhere-services.com', 3306]
dbp = ['nixonai', 'Birdie$10', '127.0.0.1', 'nixonai$fel', 'skdevil45']

print(f'We have these input values: {tup} and dbp: {dbp} and need for tunnel is {nt}')

app = Flask(__name__)
# Then tunneling to a remote database
sshtunnel.SSH_TIMEOUT = 5.0
sshtunnel.TUNNEL_TIMEOUT = 5.0

tunnel = sshtunnel.SSHTunnelForwarder(
    (tup[0]), ssh_username=tup[1], ssh_password=tup[2],
    remote_bind_address=(tup[3], tup[4])
)
tunnel.start()

SQLALCHEMY_DATABASE_URI = "mysql://{username}:{password}@{hostname}:{port}/{databasename}".format(
    username=dbp[0],
    password=dbp[1],
    hostname=dbp[2],
    port=tunnel.local_bind_port,
    databasename=dbp[3],
)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_POOL_RECYCLE"] = 299
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["DEBUG"] = True
app.secret_key = dbp[4]

db = SQLAlchemy(app)

class JO(db.Model):
    __tablename__ = 'job'
    id = db.Column('id', db.Integer, primary_key=True)
    nextid = db.Column('nextid', db.Integer)
    jo = db.Column('jo', db.String(20))
    dinc = db.Column('dinc', db.String(50))
    dexp = db.Column('dexp', db.String(50))
    date = db.Column('date', db.DateTime)
    status = db.Column('status', db.Boolean)

    def __init__(self, nextid, jo, date, status):  # , dinc, dexp,):
        self.jo = jo
        self.nextid = nextid
        self.date = date
        self.status = status

test = JO.query.filter(JO.id > 1).first()
print(f'Successfully opened tunnel to JO id {test.id}')