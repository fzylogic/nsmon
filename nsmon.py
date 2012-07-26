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
__syslog = False
__graphite = False


def _processConfig():
    nsconfig = yaml.load(conffile)
    _cfg = {
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
    return _cfg


cfg = _processConfig()


def _convert_milliseconds(timestring):
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
    __graphite = True
    try:
        sock.connect((carbon_server, carbon_port))
        sock.close()
    except Exception:
        print "Couldn't connect to %(server)s on port %(port)d,\
             is carbon-agent.py running?" \
             % {'server': carbon_server, 'port': carbon_port}
        sys.exit()


if cfg['logging']['syslog']['enabled']:
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
            for domain in cfg['domains']:
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
                        if cfg['verbose']:
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
    timeout = float(cfg['servers'][server]['timeout']) / 1000
    thread = MonThread(kwargs={'server': server,
        'timeout': timeout,
        'lock': lock,
        })
    thread.daemon = True
    thread.start()


def _gen_cmd(cmd, serverip):
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
            cmd = cmd.replace(replacement, str(cfg[replacementKey]))
        else:
            print 'cannot find ' + replacementKey + ' defined in config'
            sys.exit()
    return cmd


while (1):
    while not statusQueue.empty():
        statusline = statusQueue.get()
        [status, status_server, status_domain, status_duration] = \
        statusline.split()
        print 'processing ' + statusline
        if __graphite:
            try:
                __sock = socket()
                __sock.connect((carbon_server, carbon_port))
                if cfg['verbose']:
                    with lock:
                        print 'nsmon.responsetime.' +\
                            + status_server.replace('.', '_') \
                            + '.' + status_domain.replace('.', '_')\
                            + ' '\
                            + str(status_duration)\
                            + ' '\
                            + str(int(time()))\
                            + '\n'

                __sock.sendall('nsmon.responsetime.'
                        + status_server.replace('.', '_')
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
            os.system(_gen_cmd('serverup', status_server))
            if __syslog:
                syslog.syslog(status_server + 'recovered')
            if (len(availableServers) == cfg['min_up']):
                # We just recovered from a failure state
                # so we have to run recoverycmd
                try:
                    os.system(_gen_cmd('recovery', status_server))
                except Exception:
                    pass
                if __syslog:
                    syslog.syslog('system recovered due to ' + status_server)
        elif (status == 'BAD' and status_server in availableServers):
            availableServers.remove(status_server)
            with lock:
                print 'failing ' + status_server
            os.system(_gen_cmd('serverdown', status_server))
            if (len(availableServers) == cfg['min_up'] - 1):
                print 'only ' + str(len(availableServers)) + ' rem. servers'
                if __syslog:
                    syslog.syslog(
                        'system being retracted due to failure of '
                        + status_server)
                os.system(_gen_cmd('panic', status_server))
    sleep(1)
