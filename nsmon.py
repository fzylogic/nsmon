#!/usr/bin/env python

import DNS
import yaml
import threading
import socket
from time import sleep

conffile = open('nsconfig.yml','r')
cycles = 0
nsconfig = yaml.load(conffile)

class MonThread(threading.Thread):
  def run(self):
    print 'monitoring ' + server
    count = 0
    while (1):
      for domain in domains:
        try:
          r = DNS.Request(domain,qtype='A',server=server,timeout=timeout).req()
          if r.header['status'] != 'NOERROR':
            Error("received status of %s when attempting to query %s for NSs"%
              (r.header['status']))
          else:
            print server + ' OK'
        except DNS.SocketError:
          print str(server) + " Errored"
      sleep(frequency)
      if (cycles):
        count += 1
        if ( count >= cycles ):
          break

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
  thread.daemon=True
  thread.start()


while (1):
  sleep(1)      

