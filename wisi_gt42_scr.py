#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import xml.etree.ElementTree as ET
import requests
import os
import sys
import re
from pyzabbix import ZabbixAPI
from multiprocessing.dummy import Pool as ThreadPool

url_descr = 'http://{host}/descramble/status.xmlc'
url_name = 'http://{host}/tsdb/input.xmlc'
wisi_login = '*****'
wisi_password = '******'
zbxurl = '******'
zbxlogin = '******'
zbxpassword = '******'
wisi_login = '******'
wisi_password = '******'

def zabbix_api(zbxlogin, zbxpassword):
    GT42_ARRAY = []
    z = ZabbixAPI(url=zbxurl, user=zbxlogin, password=zbxpassword)
    zabbix_result = z.do_request('host.get',{'search':{'host':'WISI_Descrambler'},'selectInterfaces':'extend','filter':{'status':0}})["result"]
    for item in zabbix_result:
        host = item['interfaces'][0]['ip']
        hostname = item['host']
        if not re.search(r'mgmt|MGMT', hostname):
            GT42_ARRAY.append([host, hostname])
    z.do_request('user.logout')
    return GT42_ARRAY

if os.path.exists('/tmp/gt42_scr.py-lock'):
    print('Скрипт уже работает')
    os.system('/usr/bin/zabbix_sender -z ****** -p 10051 -s "Scripts_check" -k "wisi_gt42_scr" -o "LOCK_FILE"')
    sys.exit()
else:
   os.mknod('/tmp/gt42_scr.py-lock')

def module_iteration(GT42_ARRAY):
    host = GT42_ARRAY[0]
    hostname = GT42_ARRAY[1]
    srv_faild = ''
    count = 0
    print(hostname)
    descramble_xmlc = requests.get(url_descr.format(host=host), timeout=10, auth=(wisi_login, wisi_password))
    if (descramble_xmlc.status_code) != 200:
    #реализовать отправку ошибки на плату, с которой некорректно собралась xml
        print(hostname)
        #return
    try:
        descramble_tree = ET.fromstring(descramble_xmlc.content)
    except:
        print(host)
        #return
    if descramble_tree is not None:
        instances = descramble_tree.findall('./descramble/instances/instance')
        if instances is not None:
            for instance in instances:
                instance_id = int(instance.get('id'))+1
                descramble_possible = instance.get('descramble_possible')
                running = instance.get('running')
                services = instance.findall('./services/service')
                count_scrambled_srv = 0
                if services is not None:
                    for service in services:
                        service_id = service.get('id')
                        sid = service.get('sid')
                        input_id = service.get('input_id')
                        pid_list = service.findall('./pids/pid')
                        count_scrambled = 0
                        if pid_list is not None:
                            for item in pid_list:
                                pid = item.get('pid')
                                descrambled_pid = item.find('monitor')
                                descrambled_pid = descrambled_pid.get('descrambled')
                                if descrambled_pid == 'no':
                                    count_scrambled += 1
                                    count += 1
                        if count_scrambled > 0:
                            count_scrambled_srv += 1
                            name_xmlc = requests.get(url_name.format(host=host), timeout=10, auth=(wisi_login, wisi_password))
                            if (name_xmlc.status_code) == 200:
                                name_tree = ET.fromstring(name_xmlc.content)
                                ts_in = name_tree.findall('ts')
                                for ts in ts_in:
                                    services_in = ts.findall('./services/service')
                                    for service_in in services_in:
                                        sid_in = service_in.get('id')
                                        if int(sid_in) == int(sid):
                                            name_in = service_in.get('name').replace(' ','_')
                if count_scrambled_srv > 0:
                    try:
                        name_in = name_in.decode('iso-8859-5').encode('utf-8')
                    except:
                        try:
                            name_in = name_in.encode('utf-8')
                        except:
                            print('no name')
                    try:
                        send_to_zbx.write('{hostname} CI0{instance_id}_scr {name_in}_is_scrambled\n'.format(hostname=hostname, instance_id=instance_id, name_in=name_in))
                    except:
                        send_to_zbx.write('{hostname} CI0{instance_id}_scr is_scrambled\n'.format (hostname=hostname, instance_id=instance_id))
                else:
                    send_to_zbx.write('%s CI0%s_scr OK\n' % (hostname, instance_id))

try:
    GT42_ARRAY = zabbix_api(zbxlogin, zbxpassword)
except:
    os.remove('/tmp/gt42_scr.py-lock')
    os.system('/usr/bin/zabbix_sender -z ******** -p 10051 -s "Scripts_check" -k "wisi_gt42_scr" -o "ZABBIX_DB_ERR"')
    sys.exit()
with open('/tmp/wisi_gt42_scr_tmp', 'w') as send_to_zbx:
    try:
        pool = ThreadPool(1)
        pool.map(module_iteration, GT42_ARRAY)
        pool.close()
        pool.join()
    except:
        os.remove('/tmp/gt42_scr.py-lock')
        sys.exit()
os.system('/usr/bin/zabbix_sender -z ****** -p 10051 -i /tmp/wisi_gt42_scr_tmp')
os.remove('/tmp/gt42_scr.py-lock')
os.system('/usr/bin/zabbix_sender -z ****** -p 10051 -s "Scripts_check" -k "wisi_gt42_scr" -o "OK"')
