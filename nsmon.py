#!/usr/bin/env python
# vim: set syntax=python tabstop=4444 expandtab:

import DNS
import yaml
import threading
import Queue
from time import sleep

conffile = open('nsconfig.yml', 'r')
cycles = 0
nsconfig = yaml.load(conffile)


class MonThread(threading.Thread):
    def run(self):
        print 'monitoring ' + server
    count = 0
    status = 'OK'
    while (1):
        for domain in domains:
            try:
                r = DNS.Request(domain, qtype='A',
                                server=server,
                                timeout=timeout).req()
                if r.header['status'] == 'NOERROR':
                    print server + ' OK'
                if (status != 'OK'):
                    stusQueue.put('OK ' + server)
                    status = 'OK'
            except DNS.SocketError:
                print str(server) + " Errored"
                if (status != 'BAD'):
                    statusQueue.put('BAD ' + server)
                    status = 'BAD'
        sleep(frequency)
        if (cycles):
            count += 1
            if (count >= cycles):
                break
statusQueue = Queue.Queue()

availableServers = nsconfig['servers']

for server in nsconfig['servers']:
    print server + ' ' + str(nsconfig['servers'][server]['timeout'])
    domains = nsconfig['testdomains']
    frequency = nsconfig['frequency']
    try:
        cycles = nsconfig['cycles']
    except KeyError:
        pass
    timeout = nsconfig['servers'][server]['timeout']
    thread = MonThread()
    thread.daemon = True
    thread.start()


while (1):
    while not statusQueue.empty():
        statusline = statusQueue.get()
    [status, server] = statusline.split()
    print 'processing ' + statusline
    if (status == 'OK' and server in availableServers):
        availableServers.append(server)
        print 'Processing recovery of ' + server
    elif (status == 'BAD' and server in availableServers):
        availableServers.pop(server)
    sleep(1)
