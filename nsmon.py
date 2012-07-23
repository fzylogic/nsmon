#!/usr/bin/env python
# vim: set syntax=python tabstop=4 expandtab:

import DNS
import yaml
import threading
import Queue
import os
from time import sleep

conffile = open('nsconfig.yml', 'r')
cycles = 0


def processConfig():
    nsconfig = yaml.load(conffile)
    cfg = {
            'domains': nsconfig.get('testdomains'),
            'frequency': nsconfig.get('frequency', 5),
            'upcmd': nsconfig['cmds'].get('serverup'),
            'downcmd': nsconfig['cmds'].get('serverdown'),
            'paniccm': nsconfig['cmds'].get('panic'),
            'recoverycmd': nsconfig['cmds'].get('recovery'),
            'min_up': nsconfig.get('min_up', 1),
            'cycles': nsconfig.get('cycles', 0),
            'servers': nsconfig.get('servers'),
            }
    return cfg


cfg = processConfig()


class MonThread(threading.Thread):
    def run(self):
        print 'monitoring ' + server
        count = 0
        status = 'OK'
        while (1):
            for domain in cfg['domains']:
                try:
                    r = DNS.Request(domain, qtype='A',
                                    server=server,
                                    timeout=timeout).req()
                    if r.header['status'] == 'NOERROR':
                        print domain + '@' + server + ' OK'
                    if (status != 'OK'):
                        statusQueue.put('OK ' + server)
                        status = 'OK'
                except DNS.SocketError:
                    print str(server) + " Errored"
                    if (status != 'BAD'):
                        statusQueue.put('BAD ' + server)
                        status = 'BAD'
            sleep(cfg['frequency'])
            if (cycles):
                count += 1
                if (count >= cycles):
                    break

statusQueue = Queue.Queue()

availableServers = cfg['servers']

for server in cfg['servers']:
    print server + ' ' + str(cfg['servers'][server]['timeout'])
    timeout = cfg['servers'][server]['timeout']
    thread = MonThread()
    thread.daemon = True
    thread.start()


while (1):
    while not statusQueue.empty():
        statusline = statusQueue.get()
        [status, server] = statusline.split()
        print 'processing ' + statusline
        if (status == 'OK' and server not in availableServers):
            availableServers.append(server)
            print 'Processing recovery of ' + server
            os.system(cfg['upcmd'].replace('$serverip', server))
            if (len(availableServers) == cfg['min_up']):
                # We just recovered from a failure state
                # so we have to run recoverycmd
                os.system(cfg['recoverycmd'])
        elif (status == 'BAD' and server in availableServers):
            availableServers.pop(server)
            os.system(cfg['downcmd'].replace('$serverip', server))
            if (len(availableServers) == cfg['min_up'] - 1):
                os.system(cfg['paniccmd'])
        sleep(1)
