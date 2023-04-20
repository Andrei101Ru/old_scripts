#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import os
import subprocess
import json
import sys
import telnetlib
import time
import StringIO
from multiprocessing.dummy import Pool as ThreadPool
from pylockfile import * 
from pyzabbix import ZabbixAPI


def parse_result(host, hostname, discovery_stamp, bgps, msdps):
    """
    parse result from telnet session
    """
    js_msdp = '{"data":['
    js_bgp = '{"data":['
    msdp_peers = []
    bgp_peers = []
    re_ip = re.compile(r'([0-9]+)(?:\.[0-9]+){3}')
    for line in msdps:
        if re_ip.search(line):
            line = re.sub(r'\s+', ' ', line)
            line = line.split(' ')
            msdp_peers.append(line[1:])
    if msdp_peers != []:
        for peer in msdp_peers:
            peer_ip = peer[0]
            peer_state = peer[1]
            peer_uptime = peer[2]
            peer_as = peer[3]
            peer_as = 'Unknown AS' if peer_as == '?' else peer_as
            js_msdp = js_msdp + '{"{#PEER_IP}":"'+str(peer_ip)+'"},'
            msdp_params = [['Peer_State', peer_state], ['peer_uptime', peer_uptime]]
            for item in msdp_params:
                DATAFILE.write('{hostname} msdp[{PEER_IP},{msdp_key}] {msdp_data}\n'.format(hostname=hostname, PEER_IP=peer_ip,msdp_key=item[0],msdp_data=item[1]))
    for line in bgps:
        if re_ip.search(line):
            line = re.sub(r'\s+', ' ', line)
            line = line.split(' ')
            bgp_peers.append(line[1:])
    if bgp_peers != []:
        for peer in bgp_peers:
            peer_ip = peer[0]
            peer_state = peer[7]
            peer_uptime = peer[6]
            peer_as = peer[2]
            peer_rcv_pref = peer[8]
            js_bgp = js_bgp + '{"{#PEER_IP}":"'+str(peer_ip)+'", "{#PEER_AS}":"'+str(peer_as)+'"},'
            bgp_params = [['Peer_State', peer_state], ['Peer_Uptime', peer_uptime], ['Peer_rcv_pref', peer_rcv_pref]]
            for item in bgp_params:
                DATAFILE.write('{hostname} bgp[{PEER_IP},{bgp_key}] {bgp_data}\n'.format(hostname=hostname, PEER_IP=peer_ip,bgp_key=item[0],bgp_data=item[1]))

    js_msdp = js_msdp[:-1]
    js_msdp = js_msdp + ']}'
    js_bgp = js_bgp[:-1]
    js_bgp = js_bgp + ']}'
    if discovery_stamp == '1':
        if js_msdp != '{"data":]}':
            print('msdp_disc')
            os.system('/usr/bin/zabbix_sender -z 127.0.0.1 -p 10051 -s '+hostname+' -k msdp_discovery -o \'' + js_msdp + '\'')
            # print(js_msdp)
        if js_bgp != '{"data":]}':
            print('bgp_disc')
            os.system('/usr/bin/zabbix_sender -z 127.0.0.1 -p 10051 -s '+hostname+' -k bgp_mul_discovery -o \'' + js_bgp + '\'')
            # print(js_bgp)
def main_function(rsw_count):
    """
    check discovery timestamp and start telnet session and parse_result
    """
    hostname = all_rsw_name[rsw_count]
    host = all_rsw_ip[rsw_count]
    print(hostname)
    try:
        if os.path.isfile('/tmp/rsw_huawei/{host}_discovery'.format(host=host)):
            utime_change = 'stat -c %Y /tmp/rsw_huawei/{host}_discovery'.format(host=host)
            utime_now = 'date +%s'
            now = subprocess.Popen(utime_now, shell = True, stdout = subprocess.PIPE).communicate()[0]
            change = subprocess.Popen(utime_change, shell = True, stdout = subprocess.PIPE).communicate()[0]
            difference = int(now) - int(change)
            if difference>43200:
                DISCOVERYFILE = open('/tmp/rsw_huawei/{host}_discovery'.format(host=host),'w')
                DISCOVERYFILE.write('OK\n')
                discovery_stamp = '1'
                DISCOVERYFILE.close()
            else:
                discovery_stamp = '0'
        else:
            os.system('touch /tmp/rsw_huawei/{host}_discovery'.format(host=host))
            DISCOVERYFILE = open('/tmp/rsw_huawei/{host}_discovery'.format(host=host),'w')           
            DISCOVERYFILE.write('OK\n')
            DISCOVERYFILE.close()
            discovery_stamp = '1'
        def telnet_session(host):
            """
            connect each device, write commands and collect output, return output to next function.
            commands: display bgp multicast peer, display msdp brief
            """
            tn = telnetlib.Telnet(host, 23)
            time.sleep(1)
            tn.write('******\r')
            time.sleep(1)
            tn.write('******\r')
            time.sleep(1)
            tn.read_until(b'>')
            tn.write('display msdp brief\r')
            time.sleep(1)
            msdps = tn.read_until(b'>')
            tn.write('display bgp multicast peer\r')
            time.sleep(1)
            tn.read_until(b'PrefRcv', 1)
            bgps = tn.read_until(b'>', 1)
            time.sleep(1)
            tn.close()
            buf_msdps = StringIO.StringIO(msdps)
            msdps = buf_msdps.readlines()
            buf_bgps = StringIO.StringIO(bgps)
            bgps = buf_bgps.readlines()
            return bgps, msdps
        bgps, msdps = telnet_session(host)
        parse_result(host, hostname, discovery_stamp, bgps, msdps)
    except:
        print('*** FAIL: %s' % (hostname))

if __name__ == '__main__':

    zabbix = '******'
    z = ZabbixAPI(url=zabbix, user='ZabbixAPI', password='******')
    directory='/tmp/rsw_huawei'
    if not os.path.isdir(directory):
        os.makedirs(directory)
    lf = pylockfile('{directory}/rsw_lock'.format(directory=directory)) #Указание пути до файла блокировки
    lf.create()


    try:
        all_rsws_api = z.do_request("host.get",{"search":{"host":["RSW01_Huawei","RSW02_Huawei","dctvsw"]},"searchByAny":True,"selectInterfaces":["ip","type"],"selectMacros":["macro","value"],"output":["name","proxy_hostid"]})["result"]
    except Exception as zerr:
        print(zerr)
    else:
        all_rsw=''
        for host in all_rsws_api:
            for interfaces_host in host["interfaces"]:
                if "2" in interfaces_host["type"]:
                    host_ip=interfaces_host["ip"]
                    break
            hostname=host["name"]
            all_rsw+=('{hostname}|{host_ip}\n'.format(hostname=hostname, host_ip=host_ip))
        DATAFILE = open('/tmp/rsw_huawei/data_2_zabbix', 'w')

        all_rsw = all_rsw.replace('\n','|')
        all_rsw = all_rsw.split('|')[:-1]
        all_rsw_name = all_rsw[::2]
        all_rsw_ip = all_rsw[1::2]
        rsw_count = []
        i = 0
        for x in all_rsw_ip:
            rsw_count.append(int(i))
            i = i+1
        pool = ThreadPool(5)
        print(rsw_count)
        pool.map(main_function, rsw_count)
        pool.close()
        pool.join()
        DATAFILE.close()
        os.system('/usr/bin/zabbix_sender -z 127.0.0.1 -p 10051 -i /tmp/rsw_huawei/data_2_zabbix')
    finally:
        if 'z' in locals():
            z.do_request("user.logout")
        lf.delete()
        os.system('/usr/bin/zabbix_sender -z ******* -p 10051 -s "Scripts_check" -k "rsw_msdp_mbgp" -o "OK"')