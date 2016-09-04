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

    def __init__(self, config, master=None, home=None, cid=0): 
        asynchat.async_chat.__init__(self)
        self.set_terminator(b"\r\n")
        self.ibuffer = []
        self.obuffer= b""
        self.trusted = ""
        self.proxy = None
        self.vhost = "localhost"
        self.config = config
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
        if master:
            self.create_boats()
        self.hooked = {
            'PING':self.on_ping,
            'KICK':self.on_kick,
            'PRIVMSG':self.on_privmsg,
            '433':self.on_nickused,
            '001':self.on_connect,
            'JOIN':self.on_join
        }
        self.connect()

    def create_boats(self):
        self.boats = []
        self.boat_confs = self.master
        for i in range(len(self.boat_confs)):
            self.boats.append(self.__class__(self.boat_confs[i], master=None, 
                                            home=self, cid=i))
            time.sleep(5) #trying to throttle connects, not working as planned
    
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
        #doesnt work, need to match cid --> boatnet.boats.pop(self.cid)
        #quit()
        # if self.reconn:
        #     self.connect()

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
        self.nick = self.nick[:1] + random.choice("1234567890")
        self.sendline('NICK {0}'.format(self.nick))

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
        if flooding and not self.master and self.cid == nextbot and nick == boatnet.boats[lastbot].user:
            #rest of multibot flooding takes place here.
            print("Flooding True\r\n")
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
        if nick == self.trusted and self.master and trig_char == '@':
            print("Handling Commands")
            cmd = msg[0][1:]
            if cmd == 'kill':
                if len(msg) < 2:
                    self.say("[!] Not enough arguments..")
                else:
                    cid = msg[1]
                    # code to search through bots and match cid to index, will need this when handling disconnects and timeouts but for now it isnt needed
                    #idx = 0
                    #for index, worker in enumerate(self.boats):
                    #    if worker.cid == cid:
                    #        idx = index
                    #        break
                    self.boats[cid].disconnect()
                    self.boats.pop(cid)
            elif cmd == 'info':
                for bot in self.boats:
                    self.say("id: {0} user: {1} server: {2} channels: {3}".format(
                                bot.cid, bot.user, bot.server, bot.channels))
                    time.sleep(.5)
            elif cmd == 'add':
                try:
                    cid = len(boatnet.boats)
                    defig = ConfigParser()
                    defig['add'] = {'user':  msg[1],
                                    'channels': msg[2],
                                    'proxy': msg[3],
                                    'server': boatnet.server,
                                    'port': str(boatnet.port),
                                    'password': "None" }
                    newbot = dict(defig.items('add'))
                    newbot['channels'] = newbot['channels'].split(",")

                    boatnet.boats.append(boatnet.__class__(newbot, master=None, home=boatnet, cid=cid))
                    
                except IndexError:
                    self.say("[!] Not enough arguments..")     
            elif cmd == 'flood':
                #multibot flooding starts here. load the ascii, set up the variables, send the first line. when the next bot reads a message from this bot, it sends the next line.
                
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
    boatnet = Bot(master_conf, master=boat_confs)
    try:
        asyncore.loop()
    except KeyboardInterrupt:
        sys.exit(0)
