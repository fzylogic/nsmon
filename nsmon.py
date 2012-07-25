#!/usr/bin/env python
# vim: set syntax=python tabstop=4 expandtab:

import DNS
import yaml
import threading
import Queue
import re
import os
import sys
import datetime
from time import sleep
from time import time

conffile = open('nsconfig.yml', 'r')
syslog = False
graphite = False


def processConfig():
    nsconfig = yaml.load(conffile)
    cfg = {
            'verbose': nsconfig.get('verbose', False),
            'domains': nsconfig.get('testdomains'),
            'frequency': nsconfig.get('frequency', 5),
            'serverup': nsconfig['cmds'].get('serverup'),
            'serverdown': nsconfig['cmds'].get('serverdown'),
            'panic': nsconfig['cmds'].get('panic'),
            'recovery': nsconfig['cmds'].get('recovery'),
            'min_up': nsconfig.get('min_up', 1),
            'cycles': nsconfig.get('cycles', 0),
            'servers': nsconfig.get('servers'),
            'floaternet': nsconfig.get('floaternet'),
            'floaterip': nsconfig.get('floaterip'),
            'asnum': nsconfig.get('asnum', '61000'),
            'logging': {
                'graphite': {
                    'enabled': nsconfig['logging']
                            ['graphite'].get('enabled', 'no'),
                    'carbon_server': nsconfig['logging']
                            ['graphite'].get('carbon_server', '127.0.0.1'),
                    'carbon_port': nsconfig['logging']
                            ['graphite'].get('carbon_port', '127.0.0.1'),
                            },
                'syslog': {
                    'enabled': nsconfig['logging']
                            ['syslog'].get('enabled', 'no'),
                            }
                },
            }
    return cfg


cfg = processConfig()


def convertMilliseconds(timestring):
    [hours, minutes, seconds] = str(timestring).split(':')
    [seconds, microseconds] = seconds.split('.')
    milliseconds = float((float(hours) * 60 * 60 * 1000)
        + (float(minutes) * 60 * 1000)
        + (float(seconds) * 1000)
        + (float(microseconds) / 1000))
    return milliseconds


if cfg['logging']['graphite']['enabled']:
    from socket import socket
    carbon_server = cfg['logging']['graphite']['carbon_server']
    sock = socket()
    carbon_port = cfg['logging']['graphite']['carbon_port']
    graphite = True
    try:
        sock.connect((carbon_server, carbon_port))
        sock.close()
    except:
        print "Couldn't connect to %(server)s on port %(port)d,\
             is carbon-agent.py running?" \
             % {'server': carbon_server, 'port': carbon_port}
        sys.exit()


if cfg['logging']['syslog']['enabled']:
    syslog = True
    import syslog
    syslog.openlog('nsmon', 0, syslog.LOG_USER)


class MonThread(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                args=(), kwargs=None, verbose=None):
        threading.Thread.__init__(self,
                                  group=group,
                                  target=target,
                                  name=name,
                                  verbose=verbose,
                                  )
        self.args = args
        self.kwargs = kwargs
        return

    def run(self):
        serverip = self.kwargs['server']
        timeout = self.kwargs['timeout']
        lock = self.kwargs['lock']
        with lock:
            print 'monitoring ' + serverip
        if syslog:
            syslog.syslog('monitoring ' + serverip)
        count = 0
        status = 'OK'
        while (1):
            for domain in cfg['domains']:
                startTime = datetime.datetime.now()
                try:
                    r = DNS.Request(domain, qtype='A',
                                    server=serverip,
                                    timeout=timeout).req()
                    endTime = datetime.datetime.now()
                    duration = convertMilliseconds(endTime - startTime)
                    if r.header['status'] == 'NOERROR':
                        if cfg['verbose']:
                            with lock:
                                print domain + '@' + serverip + ' OK'
                    if (status == 'OK'):
                        statusQueue.put('OK'
                                + ' '
                                + serverip
                                + ' '
                                + domain
                                + ' '
                                + str(duration))
                        status = 'OK'
                except:
                    endTime = datetime.datetime.now()
                    duration = convertMilliseconds(endTime - startTime)
                    if (status != 'BAD'):
                        statusQueue.put('BAD '
                                + serverip
                                + ' '
                                + domain
                                + ' '
                                + str(duration))
                        status = 'BAD'
            sleep(cfg['frequency'])
            if (cfg['cycles']):
                count += 1
                cycles = cfg['cycles']
                if (count >= cycles):
                    break

statusQueue = Queue.Queue()

availableServers = cfg['servers'].keys()
lock = threading.Lock()
for server in cfg['servers']:
    # convert timeout config variable to a float representing
    # a fraction of a second
    timeout = int(cfg['servers'][server]['timeout']) / 1000
    thread = MonThread(kwargs={'server': server,
        'timeout': timeout,
        'lock': lock,
        })
    thread.daemon = True
    thread.start()


def genCmd(cmd, serverip):
    try:
        cmd = cfg[cmd]
    except KeyError:
        print 'cannot find cmd "' + cmd + '" in config file'
        sys.exit()
    for replacement in re.findall('\$[a-zA-Z0-9]+', cmd):
        replacementKey = replacement.replace('$', '')
        if replacementKey == 'serverip':
            cmd = cmd.replace(replacement, serverip)
        elif replacementKey in cfg:
            cmd = cmd.replace(replacement, cfg[replacementKey])
        else:
            print 'cannot find ' + replacementKey + ' defined in config'
            sys.exit()
    return cmd


while (1):
    while not statusQueue.empty():
        statusline = statusQueue.get()
        [status, server, domain, duration] = statusline.split()
        if graphite:
            try:
                sock = socket()
                sock.connect((carbon_server, carbon_port))
                if cfg['verbose']:
                    with lock:
                        print 'nsmon.responsetime.' +\
                            + server.replace('.', '_') \
                            + '.' + domain.replace('.', '_')\
                            + ' '\
                            + str(duration)\
                            + ' '\
                            + str(int(time()))\
                            + '\n'

                sock.sendall('nsmon.responsetime.' + server.replace('.', '_')
                        + '.' + domain.replace('.', '_')
                        + ' '
                        + str(duration)
                        + ' '
                        + str(int(time()))
                        + '\n')
                sock.close()
            except:
                with lock:
                    print 'cannot contact carbon server'
        if (status == 'OK' and server not in availableServers):
            availableServers.append(server)
            with lock:
                print 'Processing recovery of ' + server
            os.system(genCmd('serverup', server))
            if syslog:
                syslog.syslog(server + 'recovered')
            if (len(availableServers) == cfg['min_up']):
                # We just recovered from a failure state
                # so we have to run recoverycmd
                os.system(genCmd('recovery', server))
                if syslog:
                    syslog.syslog('system recovered due to ' + server)
        elif (status == 'BAD' and server in availableServers):
            availableServers.remove(server)
            with lock:
                print 'failing ' + server
            os.system(genCmd('serverdown', server))
            if (len(availableServers) == cfg['min_up'] - 1):
                if syslog:
                    syslog.syslog(
                        'system being retracted due to failure of ' + server)
                os.system(genCmd('paniccmd', server))
        sleep(1)
