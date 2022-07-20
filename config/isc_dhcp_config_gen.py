import csv
import io
import ipaddress
import json
import os
import pathlib
import yaml


indexes = range(1,10)


def index_check(index):
    return indexes.index(index)


def vrf(index):
    index_check(index)
    return 'VRF' + (index * 10)


def ip_network(index, ipaddr):
    index_check(index)
    parts = ipaddr.exploded
    assert parts[0] == 10
    # Increment part C
    parts[2] = parts[2] + (index * 10)
    return ipaddress.IPv4Network(parts + '/24')


def class_b_part(ipaddr: ipaddress.IPv4Address):
    parts = ipaddr.exploded
    return parts[1]


def vlan(index, vlan_offset):
    index_check(index)
    return vlan_offset + index * 10


vrf_descs_in_order = {
    'wireless-ap-mgmt',
    'it-netnisser',
    'STAB',
    'IP Telefoni',
    'Beredskabet',
    'hotspot',
    'Video',
    'Skejser'
}


def vrf_desc(index):
    index_check(index)
    return vrf_descs_in_order[index - 1]


class ConfigRow:
    def __init__(self, main_name, sec_name, ip_value, vlan_value):
        self.main_name = main_name
        self.sec_name = sec_name
        self.ip_value = ip_value
        self.vlan_value = vlan_value


def read_yaml_as_dict(configfile):
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
                        print('main: ' + main_name + ' sec: ' + sec_name + ' ip: ' + ip_value + ' vlan: ' + str(
                            vlan_value))
                        yield ConfigRow(main_name, sec_name, ip_value, vlan_value)


def map_pre_to_post_config(config_rows):
    for input_row in config_rows:
        base_ip_addr = ipaddress.IPv4Address(input_row.ip_value)
        for index in indexes:
            # prefix, vrf, tenant, site, vlan_group, vlan, status, role, is_pool, description
            # 10.0.0.0/30,NPFLAN,,npflan,npflan-core1,301,Active,Firewall Net,,AVATAR Inside
            yield {
                'prefix': ip_network(index, base_ip_addr),
                'vrf': vrf(index),
                'tenant': 'SL2022',
                'site': 'sl2022',
                'vlan_group': vrf_desc(index),
                'vlan': vlan(index, input_row.vlan_value),
                'status': 'Active',
                'role': 'n/a',
                'is_pool': '',
                'description': input_row.main_name + ' - ' + input_row.sec_name
            }

def write_data_file(input_dict, outputfilename):
    with open(outputfilename, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=input_dict.keys())

        writer.writeheader()
        writer.writerows(input_dict)

def subnet(row):
    if row['role'].casefold() not in ['access', 'wireless', 'management  netværk', 'management netværk', 'cctv',
                                      'management access points', 'environment']:
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
                "pool": str(ip[poolstart]) + "-" + str(ip[pow(2, (32 - ip.prefixlen)) - 6])
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


#predatafile = pathlib.Path(os.path.dirname(__file__), 'pre-data.csv')
configfile = pathlib.Path(os.path.dirname(__file__), 'full-config.yaml')
datafile = pathlib.Path(os.path.dirname(__file__), 'data.csv')
#if predatafile.exists() and predatafile.is_file():
    # Pre-data file exists. Intention is to generate a data file.
#    pre = predatafile.read_bytes()
#    prereader = csv.DictReader(io.StringIO(pre.decode()), delimiter=',', quotechar='|')
#    with open(datafile, 'wb+') as f:
#        print('hest')
#else:
#    print('No pre-data.csv file found')
if not configfile.exists() or not configfile.is_file():
    raise FileNotFoundError(configfile)
else:
    config_dict = read_yaml_as_dict(configfile)
    post_config = map_pre_to_post_config(config_dict)


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
