
def getpaths(machine,pathto):
    if machine == 'ubuntu1700':
        if pathto == 'dropbox': return '/mnt/Ubuntu1TB01/Dropbox'
        if pathto == 'system': return '/mnt/Ubuntu1TB01/Dropbox/system'
        if pathto == 'working': return '/home/mark/flask/agents'
    elif machine == 'mserver':
        if pathto == 'dropbox': return '/home/mark/Dropbox'
        if pathto == 'system': return '/home/mark/Dropbox/system'
        if pathto == 'working': return '/home/mark/flask/agents'
    elif machine == 'bee1':
        if pathto == 'dropbox': return '/home/disp1/Dropbox'
        if pathto == 'system': return '/home/disp1/Dropbox/system'
        if pathto == 'working': return '/home/disp1/flask/agents'
    elif machine == 'asusvivo':
        if pathto == 'dropbox': return '/home/mark/Dropbox'
        if pathto == 'system': return '/home/mark/Dropbox/system'
        if pathto == 'working': return '/home/mark/flask/agents'
    else:
        return '/home/mark/Dropbox'


def d2s(instr):
    try:
        instr = instr.replace('$', '').replace(',', '')
    except:
        instr = str(instr)
    try:
        infloat = float(instr)
        outstr = "%0.2f" % infloat
    except:
        outstr = instr
    return outstr

def d2f(instr):
    try:
        instr = instr.replace('$', '').replace(',', '')
    except:
        instr = str(instr)
    try:
        infloat = float(instr)
        outstr = "%0.2f" % infloat
    except:
        outstr = instr
    return float(outstr)

def d1s(instr):
    try:
        instr = instr.replace('$', '').replace(',', '')
    except:
        instr = str(instr)
    try:
        infloat = float(instr)
        outstr = "%0.1f" % infloat
    except:
        outstr = instr
    return outstr

def avg(in1,in2):
    out=(in1+in2)/2
    return out

def commaguard(instring):
    sandwich=re.compile(r',[A-Za-z]')
    t1=sandwich.findall(instring)
    for t in t1:
        l=t[1]
        instring=instring.replace(t,', '+l)
    return instring

def parseline(line,j):
    splitline=line.split()
    outlines=[]
    newline=''
    for word in splitline:
        if len(newline)<j-7:
            newline=newline+word+' '
        else:
            outlines.append(newline)
            newline=word+' '
    outlines.append(newline)
    return outlines

def hasinput(input):
    if input is None:
        return 0
    elif isinstance(input,str):
        input = input.strip()
        if input == '' or input == 'None' or input == 'none' or input=='0' or input.lower()=='nay':
            return 0
        else:
            return 1
    elif isinstance(input,int):
        if input == 0:
            return 0
        else:
            return 1
    else:
        return 1

def stripper(input):
    try:
        new = input.strip()
    except:
        new = ''
    return new