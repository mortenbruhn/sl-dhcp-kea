import csv
import io
import ipaddress
import json
import os
import pathlib
import yaml


def subnet(row):
    if row['role'].casefold() not in ['access', 'wireless', 'management  netværk', 'management netværk', 'cctv','management access points', 'environment']:
        return
    if row['description'].casefold() in ['wireless networks']:
        return
    ip = ipaddress.IPv4Network(row['prefix'])

    poolstart = 11
    # if ip.subnet_of(ipaddress.IPv4Network('10.255.0.0/16')) or \
    #         ip.subnet_of(ipaddress.IPv4Network('172.20.0.0/16')):
    #     poolstart = 100
    # elif ip.subnet_of(ipaddress.IPv4Network('10.248.0.0/16')):
    #     poolstart = 6

    if ip.prefixlen > 24:
        return
    return {
        "subnet": ip.with_prefixlen,
        "pools": [
          {
              "pool":  str(ip[poolstart]) + "-" + str(ip[pow(2, (32-ip.prefixlen))-6])
          }
        ],
        "relay": {
            "ip-address": str(ip[1])
        },
        "option-data": [
            {
                "name": "routers",
                "data": str(ip[1])
            }
        ]
    }

predatafile = pathlib.Path(os.path.dirname(__file__), 'pre-data.csv')
configfile = pathlib.Path(os.path.dirname(__file__), 'full-config.yaml')
with open(configfile, 'r') as c:
    main_list = yaml.safe_load(c)
    for main_item in main_list:
        for main_key, main_value in main_item.items():
            print('Generating config for main IS with key ' + main_key)
            main_name = main_key
            for second_item in main_value:
                for sec_key, sec_value in second_item.items():
                    sec_name = sec_key
                    ip_value = sec_value['ip']
                    vlan_value = sec_value['vlan']
                    print('main: ' + main_name + ' sec: ' + sec_name + ' ip: ' + ip_value + ' vlan: ' + str(vlan_value))
datafile = pathlib.Path(os.path.dirname(__file__), 'data.csv')
if predatafile.exists() and predatafile.is_file():
    # Pre-data file exists. Intention is to generate a data file.
    pre = predatafile.read_bytes()
    prereader = csv.DictReader(io.StringIO(pre.decode()), delimiter=',', quotechar='|')
    with open(datafile, 'wb+') as f:
        print('hest')
else:
    print('No pre-data.csv file found')

if not datafile.exists() or not datafile.is_file():
    # netbox = 'https://netbox.minserver.dk/ipam/prefixes/?status=1&parent=&family=&q=&vrf=npflan&mask_length=&export'
    # data = urllib.request.urlopen(netbox).read()
    # with open(datafile, 'wb+') as f:
    #     f.write(data)
    raise Exception('Expected a CSV file to be found at ' + datafile.name + '. No such file found.')
else:
    data = datafile.read_bytes()

reader = csv.DictReader(io.StringIO(data.decode()),
                        delimiter=',', quotechar='|')
print('"subnet4":')
print(
    json.dumps(
        list(filter(None, (subnet(row) for row in reader))),
        indent=True
    )
)
