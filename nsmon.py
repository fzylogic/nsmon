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

__syslog = False
__graphite = False


class NsConfig:
    conffile = open('nsconfig.yml', 'r')
    nsconfig = yaml.load(conffile)

    def domains(self):
        return self.nsconfig.get('testdomains', [])

    def verbose(self):
        return self.nsconfig.get('verbose', False)

    def frequency(self):
        return self.nsconfig.get('frequency', 5)

    def min_up(self):
        return self.nsconfig.get('min_up', 1)

    def get_cmd(self, cmd):
        return self.nsconfig['cmds'].get(cmd, '/usr/bin/true')

    def generate_cmd(self, cmd_alias, serverip):
        full_cmd = self.get_cmd(cmd_alias)
        for replacement in re.findall('\$[a-zA-Z0-9]+', full_cmd):
            replacementKey = replacement.replace('$', '')
            if replacementKey == 'serverip':
                full_cmd = full_cmd.replace(replacement, serverip)
            elif replacementKey in self.nsconfig:
                full_cmd = full_cmd.replace(replacement,
                        str(self.nsconfig[replacementKey]))
            else:
                    print 'cannot find ' + replacementKey \
                            + ' defined in config'
            return full_cmd

    def serverup(self):
        return self.nsconfig['cmds'].get('serverup', '/usr/bin/true')

    def serverdown(self):
        return self.nsconfig['cmds'].get('serverdown', '/usr/bin/true')

    def panic(self):
        return self.nsconfig['cmds'].get('panic', '/usr/bin/true')

    def recovery(self):
        return self.nsconfig['cmds'].get('panic', '/usr/bin/true')

    def servers(self):
        return self.nsconfig.get('servers', [])

    def floaternet(self):
        return self.nsconfig.get('floaternet', '')

    def floaterip(self):
        return self.nsconfig.get('floaterip', '')

    def asnum(self):
        return self.nsconfig.get('asnum', 60001)

    def logging(self):
        return self.nsconfig.get('logging', {})

    def cycles(self):
        return self.nsconfig.get('cycles', False)


config = NsConfig()


def _convert_milliseconds(timestring):
    [hours, minutes, seconds] = str(timestring).split(':')
    [seconds, microseconds] = seconds.split('.')
    milliseconds = float((float(hours) * 60 * 60 * 1000)
        + (float(minutes) * 60 * 1000)
        + (float(seconds) * 1000)
        + (float(microseconds) / 1000))
    return milliseconds


if config.logging()['graphite']['enabled']:
    from socket import socket
    carbon_server = config.logging()['graphite']['carbon_server']
    sock = socket()
    carbon_port = config.logging()['graphite']['carbon_port']
    __graphite = True
    try:
        sock.connect((carbon_server, carbon_port))
        sock.close()
    except Exception:
        print "Couldn't connect to %(server)s on port %(port)d,\
             is carbon-agent.py running?" \
             % {'server': carbon_server, 'port': carbon_port}
        sys.exit()


if config.logging()['syslog']['enabled']:
    __syslog = True
    import syslog
    syslog.openlog('nsmon', 0, syslog.LOG_USER)


class MonThread(threading.Thread):
    """Thread subclass for server monitoring"""
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
        serverip = threading.local()
        timeout = threading.local()
        serverip = self.kwargs['server']
        timeout = self.kwargs['timeout']
        _lock = self.kwargs['lock']
        with _lock:
            print 'monitoring ' + serverip + ' with timeout '\
                    + str(timeout)
        if syslog:
            syslog.syslog('monitoring ' + serverip)
        count = 0
        while (1):
            for domain in config.domains():
                startTime = datetime.datetime.now()
                try:
                    req = threading.local()
                    req = DNS.Request(domain, qtype='A',
                                    server=serverip,
                                    timeout=timeout).req()
                    endTime = datetime.datetime.now()
                    duration = threading.local()
                    duration = _convert_milliseconds(endTime - startTime)
                    if req.header['status'] == 'NOERROR':
                        if config.verbose():
                            with _lock:
                                print domain + '@' + serverip + ' OK'
                        statusQueue.put('OK'
                                + ' '
                                + serverip
                                + ' '
                                + domain
                                + ' '
                                + str(duration))
                except Exception:
                    endTime = datetime.datetime.now()
                    duration = _convert_milliseconds(endTime - startTime)
                    statusQueue.put('BAD '
                            + serverip
                            + ' '
                            + domain
                            + ' '
                            + str(duration))
            sleep(config.frequency())
            if (config.cycles()):
                count += 1
                cycles = config.cycles()
                if (count >= cycles):
                    break

statusQueue = Queue.Queue()

availableServers = config.servers().keys()
lock = threading.Lock()
for server in config.servers():
    # convert timeout config variable to a float representing
    # a fraction of a second
    timeout = float(config.servers()[server]['timeout']) / 1000
    thread = MonThread(kwargs={'server': server,
        'timeout': timeout,
        'lock': lock,
        })
    thread.daemon = True
    thread.start()


while (1):
    while not statusQueue.empty():
        statusline = statusQueue.get()
        [status, status_server, status_domain, status_duration] = \
        statusline.split()
        print 'processing ' + statusline
        try:
            servername = config.servers()[status_server]['name']
        except KeyError:
            servername = status_server.replace('.', '_')
        if __graphite:
            try:
                __sock = socket()
                __sock.connect((carbon_server, carbon_port))
                if config.verbose():
                    with lock:
                        print 'nsmon.responsetime.' +\
                            + servername \
                            + '.' + status_domain.replace('.', '_')\
                            + ' '\
                            + str(status_duration)\
                            + ' '\
                            + str(int(time()))\
                            + '\n'

                __sock.sendall('nsmon.responsetime.'
                        + servername
                        + '.' + status_domain.replace('.', '_')
                        + ' '
                        + str(status_duration)
                        + ' '
                        + str(int(time()))
                        + '\n')
                __sock.close()
            except Exception:
                with lock:
                    print 'cannot contact carbon server'
        if (status == 'OK' and status_server not in availableServers):
            availableServers.append(status_server)
            with lock:
                print 'Processing recovery of ' + status_server
            os.system(config.generate_cmd('serverup', status_server))
            if __syslog:
                syslog.syslog(status_server + 'recovered')
            if (len(availableServers) == config.min_up()):
                # We just recovered from a failure state
                # so we have to run recoverycmd
                try:
                    os.system(config.generate_cmd('recovery', status_server))
                except Exception:
                    pass
                if __syslog:
                    syslog.syslog('system recovered due to ' + status_server)
        elif (status == 'BAD' and status_server in availableServers):
            availableServers.remove(status_server)
            with lock:
                print 'failing ' + status_server
            os.system(config.generate_cmd('serverdown', status_server))
            if (len(availableServers) == config.min_up() - 1):
                print 'only ' + str(len(availableServers)) + ' rem. servers'
                if __syslog:
                    syslog.syslog(
                        'system being retracted due to failure of '
                        + status_server)
                os.system(config.generate_cmd('panic', status_server))
    sleep(0.1)
