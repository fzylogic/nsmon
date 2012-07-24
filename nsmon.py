#!/usr/bin/env python
# vim: set syntax=python tabstop=4 expandtab:

import DNS
import yaml
import threading
import Queue
import re
import os
import sys
from time import sleep

conffile = open('nsconfig.yml', 'r')


def processConfig():
    nsconfig = yaml.load(conffile)
    cfg = {
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
            }
    return cfg


cfg = processConfig()


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
        print 'monitoring ' + serverip
        count = 0
        status = 'OK'
        while (1):
            for domain in cfg['domains']:
                try:
                    r = DNS.Request(domain, qtype='A',
                                    server=serverip,
                                    timeout=timeout).req()
                    if r.header['status'] == 'NOERROR':
                        print domain + '@' + serverip + ' OK'
                    if (status != 'OK'):
                        statusQueue.put('OK ' + serverip)
                        status = 'OK'
                except DNS.SocketError:
                    print str(serverip) + " Errored"
                    if (status != 'BAD'):
                        statusQueue.put('BAD ' + serverip)
                        status = 'BAD'
            sleep(cfg['frequency'])
            if (cfg['cycles']):
                count += 1
                cycles = cfg['cycles']
                if (count >= cycles):
                    break

statusQueue = Queue.Queue()

availableServers = cfg['servers'].keys()

for server in cfg['servers']:
    #print server + ' ' + str(cfg['servers'][server]['timeout'])
    timeout = cfg['servers'][server]['timeout']
    thread = MonThread(kwargs={'server': server})
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
            print 'replacing ' + replacement + ' with ' + serverip
            cmd = cmd.replace(replacement, serverip)
        elif replacementKey in cfg:
            print 'replacing ' + replacement + ' with ' + cfg[replacementKey]
            cmd = cmd.replace(replacement, cfg[replacementKey])
        else:
            print 'cannot find ' + replacementKey + ' defined in config'
            sys.exit()
    print 'cmd = ' + cmd
    return cmd


while (1):
    while not statusQueue.empty():
        statusline = statusQueue.get()
        [status, server] = statusline.split()
        print 'processing ' + statusline
        if (status == 'OK' and server not in availableServers):
            availableServers.append(server)
            print 'Processing recovery of ' + server
            os.system(genCmd('serverup', server))
            if (len(availableServers) == cfg['min_up']):
                # We just recovered from a failure state
                # so we have to run recoverycmd
                os.system(genCmd('recovery', server))
        elif (status == 'BAD' and server in availableServers):
            availableServers.remove(server)
            print 'failing ' + server
            #os.system(genCmd('serverdown', server))
            if (len(availableServers) == cfg['min_up'] - 1):
                os.system(genCmd('paniccmd', server))
        sleep(1)
