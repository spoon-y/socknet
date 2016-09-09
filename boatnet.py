import asyncore, asynchat
import socket
import sys
from configparser import ConfigParser
import time
import random
#based on erm's boatnet.py 
#https://github.com/erm/boatnet/tree/e4090eeb68d633d82e088e40ec967fc98efc026e

#requires modified asyncore.py to support pysocks on non blocking sockets
#also probably needs asynchat.py modified to fix push() bug

#todo
#fix push() cutting off line after a space is sent
#timeouts for sockets
#handle errors
#handle disconnects
#import list of proxies to use in case of disconnect/


#vars for multibot flooding
lastbot = 0
nextbot = 1
flooding = False
ascii = []
lastlineidx = 0

class Bot(asynchat.async_chat):

    def collect_incoming_data(self, data):
        self.ibuffer.append(data.decode('utf-8'))

    def __init__(self, config, master=None, home=None, cid=0, ismaster=False): 
        asynchat.async_chat.__init__(self)
        self.set_terminator(b"\r\n")
        self.ibuffer = []
        self.boats = []
        self.obuffer= b""
        self.trusted = ""
        self.proxy = None
        self.vhost = "localhost"
        self.config = config
        self.ismaster = ismaster
        for opt, val in self.config.items():
            setattr(self, opt, val)
        try:
            self.server, self.user
        except AttributeError:
            print("[!] Error: Not enough arguments")
            sys.exit(0)
        self.port = int(self.port)
        self.nick = self.real = self.user
        self.quit = "good bye"
        self.reconn = True
        self.cid = cid
        self.master = master
        self.home = home
        self.delay = 30
        if master:
            self.boats = []
            self.last_connected = time.time()
        self.hooked = {
            'PING':self.on_ping,
            'KICK':self.on_kick,
            'PRIVMSG':self.on_privmsg,
            '433':self.on_nickused,
            '001':self.on_connect,
            'JOIN':self.on_join,
            'ERROR':self.on_error
        }
        self.connect()

    def ordercid(self):
        for i in range(len(self.boats)):
            self.boats[i].cid = i

    def readable(self):
        if self.master:
            if self.last_connected + self.delay < time.time():
                boat = self.master.pop()
                if not self.boats:
                    cid = 0
                else:
                    cid = len(self.boats) + 1
                self.boats.append(self.__class__(boat, master=None, home=self, cid=cid))
                self.last_connected = time.time()
        return True
    
    def connect(self):
        if self.vhost != 'localhost':
            raw_ip = socket.getaddrinfo(self.vhost, 0)[0][4][0]
            if ':' in raw_ip:
             self.create_socket(socket.AF_INET6, socket.SOCK_STREAM, proxy=self.proxy)
            else:
                self.create_socket(socket.AF_INET, socket.SOCK_STREAM, proxy=self.proxy)
            self.bind((self.vhost,0))
        else:
            self.create_socket(socket.AF_INET, socket.SOCK_STREAM, proxy=self.proxy)
        if self.password != "None":
            self.sendline('PASS {0}'.format(self.password))
        asynchat.async_chat.connect(self, (self.server, self.port))
        print("[!] {0} connecting to {1} on port {2}".format(self.nick, 
                                                            self.server, 
                                                            self.port))

    def disconnect(self):
        if self.reconn:
            self.reconn = False
        self.sendline('QUIT :{0}'.format(self.quit))
        print("[!] {0} disconnecting from {1}".format(self.nick, self.server))
        self.close()
        #if self.reconn:
        #    self.connect()

    def handle_connect(self):
        print("Handling Connect")
        self.sendline('USER {0} * * :{1}'.format(self.user, self.real))
        self.sendline('NICK {0}'.format(self.nick))
        print("[!] {0} connected!".format(self.nick))

    def handle_close(self):
        print("Handling Close")
        self.close()
        if not self.ismaster:
            boatnet.boats.pop(self.cid)
            boatnet.ordercid()
        else:
            print("Master died. Reconnecting...")
            self.connect()

    def sendline(self, line):
        self.push(bytes(line + '\r\n', "UTF-8"))
        print('Sending: ' + line + '\r\n')

    def hook(self, command, function):
        if command not in self.hooked:
            self.hooked[command] = []
        if function not in self.hooked[command]:
            self.hooked[command].append(function)
                
    def recvline(self, prefix, command, params):
        i = self.hooked.get(command)
        if i:
            i(prefix, params)
            return 

    def parseline(self, data):
        prefix = ''
        trailing = []
        data = data.strip("[\'\']")
        if not data:
            pass
        if data[0] == ':':
            prefix, data = data[1:].split(' ', 1)
        if data.find(' :') != -1:
            data, trailing = data.split(' :', 1)
            params = data.split()
            params.append(trailing)
        else:
            params = data[0].split()
        command = params.pop(0)
        return prefix, command, params

    def found_terminator(self):
        data = ''.join(str(self.ibuffer))
        self.ibuffer = []
        print("RAW: " + data)
        prefix, command, params = self.parseline(data)
        self.recvline(prefix, command, params)
        
    def on_ping(self, prefix, params):
        self.sendline('PONG {0}'.format(' '.join(params)))

    def on_connect(self, prefix, params):
        self.connected = True
        for chan in self.channels:
            self.joinchan(chan)
            print("[!] Joining {0}".format(chan))
    
    def on_join(self, prefix, params):
        nick = prefix.split('!')[0]
        if nick == self.nick:
            channel = params[0]
            if channel not in [chan for chan in self.channels]:
                self.channels.append(channel)

    def on_kick(self, prefix, params):
        nick = prefix.split('!')[0]
        channel = params[0]
        print("[!] {0} was kicked from {1}".format(nick, channel))

    def on_nickused(self, prefix, params):
        self.nick = self.nick[:-1] + random.choice("1234567890")
        self.sendline('NICK {0}'.format(self.nick))

    def on_error(self, prefix, params):
        print("Error {0} {1}".format(prefix, params))
        self.disconnect()

    def on_privmsg(self, prefix, params):
        
        global lastbot
        global nextbot
        global lastline
        global flooding
        global ascii
        global lastlineidx
        nick = prefix.split('!')[0]
        channel = params[0]
        msg = params[1].split()
        if flooding and not self.ismaster and self.cid == nextbot and nick == boatnet.boats[lastbot].nick:
            #rest of multibot flooding takes place here.
            time.sleep(.08)
            lastbot = nextbot
            nextbot += 1
            if nextbot > len(boatnet.boats) - 1:
                nextbot = 0
            lastlineidx += 1
            if lastlineidx > len(ascii) - 1:
                flooding = False            
            else:
                self.say(ascii[lastlineidx])
            
        trig_char = msg[0][0]
        chan_msg = msg[0:]
        if nick == self.trusted and self.ismaster and trig_char == '@':
            print("Handling Commands")
            cmd = msg[0][1:]
            if cmd == 'kill':
                if len(msg) < 2:
                    self.say("[!] Not enough arguments..")
                else:
                    cid = int(msg[1])
                    if cid <= len(self.boats) - 1: 
                        self.boats[cid].disconnect() 
                    else: 
                        self.say("[!] ID not in range.")
            elif cmd == 'info':
                try:
                    for bot in self.boats:
                        self.say("id: {0} user: {1} server: {2} channels: {3}".format(
                                    bot.cid, bot.user, bot.server, bot.channels))
                        time.sleep(.5)
                except:
                    self.say("[!] Error. Did you generate any connections?")
            elif cmd == 'add':
                try:
                    cid = len(self.boats)
                    newbot = {'user':  msg[1],
                              'channels': msg[2],
                              'proxy': msg[3],
                              'server': boatnet.server,
                              'port': str(boatnet.port),
                              'password': "None" }
                    newbot['channels'] = newbot['channels'].split(",")

                    boatnet.boats.append(boatnet.__class__(newbot, master=None, home=boatnet, cid=cid))
                    
                except IndexError:
                    self.say("[!] Not enough arguments..")     
            elif cmd == 'flood':
                #multibot flooding starts here. load the ascii, set up the variables, send the first line. when the next bot reads a message from this bot, it sends the next line.
                self.ordercid()
                print("Ascii=" + msg[1] + "\r\n")
                try:
                    afile = msg[1].replace("\\","")
                    afile = afile.replace("/","")
                    print('Flooding ' + channel + ' with ' + afile)
                    f = open("../ascii/" + afile + ".txt", encoding="latin-1")
                    ascii = f.read().splitlines()
                    f.close()
                    lastlineidx = 0
                    lastbot = 0
                    nextbot = 1
                    if nextbot > len(self.boats) - 1:
                        nextbot = 0 
                    flooding = True
                    self.boats[0].say(ascii[0])
                except IOError:
                    print('File input error.')
                except UnicodeDecodeError:
                    print("Decode error.")
            elif cmd == 'fflood':
                #testing quicker flooding
                self.ordercid()
                print("Ascii=" + msg[1] + "\r\n")
                try:
                    afile = msg[1].replace("\\","")
                    afile = afile.replace("/","")
                    print('Flooding with ' + afile)
                    f = open("../ascii/" + afile + ".txt", encoding="latin-1")
                    ascii = f.read().splitlines()
                    f.close()
                    nextbot = 0
                    for line in ascii:
                        self.boats[nextbot].say(line)
                        time.sleep(.1)
                        if nextbot + 1 > len(self.boats) - 1:
                            nextbot = 0 
                        else:
                            nextbot +=1
                except IOError:
                    print('File input error.')
                except UnicodeDecodeError:
                    print("Decode error.")
            else:
                self.say("[!] Command no found...")

    def say(self, line):
        line = line.replace(" ",".") #asynchat is fucking up when sending spaces, need to check asynchat.py push() method
        self.sendline('PRIVMSG {0} {1}'.format(self.channels[0], line))

    def partchan(self, chan, reason):
        self.sendline('PART {0} {1}'.format(chan, reason))

    def joinchan(self, chan):
        self.sendline('JOIN {0}'.format(chan))


if __name__ == '__main__':
    boat_confs = []
    config = ConfigParser()
    config.read("boats.ini")
    sections = dict(config._sections)
    for section_name in config.sections():
        if section_name == 'master':
            master_conf = dict(config.items(section_name))
            master_conf['channels'] = master_conf['channels'].split(',')
        else:
            _boat_conf = dict(config.items(section_name))
            _boat_conf['channels'] = _boat_conf['channels'].split(',')
            boat_confs.append(_boat_conf)
    boatnet = Bot(master_conf, master=boat_confs, ismaster=True)
    try:
        asyncore.loop()
    except KeyboardInterrupt:
        sys.exit(0)
