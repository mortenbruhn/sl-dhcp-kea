import csv
import io
import ipaddress
import json
import os
import pathlib
import yaml


class ConfigRow:
    def __init__(
            self,
            main_name,
            sec_name,
            ip_value,
            vlan_value,
            offsets,
            vrf_incr,
            ip_c_incr,
            vlan_incr,
            cidr_subnet,
            indexes
    ):
        self.main_name = main_name
        self.sec_name = sec_name
        self.ip_value = ip_value
        self.vlan_value = vlan_value
        self.offsets = offsets
        self.vrf_incr = vrf_incr
        self.ip_c_incr = ip_c_incr
        self.vlan_incr = vlan_incr
        self.cidr_subnet = cidr_subnet
        self.indexes = indexes
        self.vrf_desc_dict = {
            'VRF10': 'wireless-ap-mgmt',
            'VRF20': 'it-netnisser',
            'VRF30': 'STAB',
            'VRF40': 'IP Telefoni',
            'VRF50': 'Beredskabet',
            'VRF60': 'hotspot',
            'VRF70': 'Video',
            'VRF90': 'Skejser'
        }

    def network(self, value):
        return str(ipaddress.IPv4Network(
            value + ('/' +
                     str(self.cidr_subnet)
                     if not (value.__contains__('/')) else
                     ""
                     ), strict=False))

    def index_check(self, index):
        return self.indexes.index(index)

    def ip_network(self, index, ip):
        self.index_check(index)
        parts = ip.split('.')
        if int(parts[0]) != 10:
            raise ValueError('Unexpected value: ' + parts[0])
        # Increment part C

        parts[2] = str(int(parts[2]) + (self.offsets[index - 1] * self.ip_c_incr))
        return self.network('.'.join(parts))

    def class_b_part(self, ipaddr: ipaddress.IPv4Address):
        parts = ipaddr.exploded
        return parts[1]

    def vlan(self, index, vlan_offset):
        self.index_check(index)
        return vlan_offset + self.offsets[index - 1] * self.vlan_incr

    def vrf_desc(self, vfr): pass
    def vrf_id(self, index): pass


class WiredConfigRow(ConfigRow):
    def __init__(self, main_name, sec_name, ip_value, vlan_value):
        super().__init__(
            main_name,
            sec_name,
            ip_value,
            vlan_value,
            [1, 2, 3, 4, 5, 6, 7, 9],
            10,
            10,
            10,
            24,
            range(1, 9)
        )

    def vrf_desc(self, vfr):
        return self.vrf_desc_dict[vfr]

    def vrf_id(self, index):
        self.index_check(index)
        return 'VRF' + str((self.offsets[index - 1] * self.vrf_incr))


class WirelessConfigRow(ConfigRow):
    def __init__(self, main_name, sec_name, ip_value, vlan_value, vrf='VRF60'):
        super().__init__(
            main_name,
            sec_name,
            ip_value,
            vlan_value,
            range(0, 8),
            10,
            10,
            0,
            20,
            range(1, 2)
        )
        self.vrf = vrf

    def vrf_desc(self, vrf):
        return self.vrf_desc_dict[self.vrf]

    def vrf_id(self, index):
        return self.vrf


wired_config_name = 'wired-config.yaml'
wifi_config_name = 'wifi-config.yaml'
config_file_names = [wired_config_name, wifi_config_name]
data_file_name = 'data.csv'
default_pool_start = 16
wlan_controller_ip = '10.255.10.10'


def read_yaml_as_dict(configfile, wireless=False):
    result = []
    with open(configfile, 'r') as c:
        main_list = yaml.safe_load(c)
        for main_item in main_list:
            for main_key, main_value in main_item.items():
                main_name = main_key
                for second_item in main_value:
                    for sec_key, sec_value in second_item.items():
                        sec_name = sec_key
                        ip_value = sec_value['ip']
                        vlan_value = sec_value['vlan']
                        result.append(
                            WirelessConfigRow(main_name, sec_name, ip_value, vlan_value, sec_value['vrf'])
                            if wireless else
                            WiredConfigRow(main_name, sec_name, ip_value, vlan_value)
                        )
    return result


def map_pre_to_post_config(config_rows):
    result = []
    for input_row in config_rows:
        for index in input_row.indexes:
            # prefix, vrf, tenant, site, vlan_group, vlan, status, role, is_pool, description
            # 10.0.0.0/30,NPFLAN,,npflan,npflan-core1,301,Active,Firewall Net,,AVATAR Inside
            result.append({
                'prefix': input_row.ip_network(index, input_row.ip_value),
                'vrf': input_row.vrf_id(index),
                'tenant': 'SL2022',
                'site': 'sl2022',
                'vlan_group': input_row.vrf_desc(input_row.vrf_id(index)),
                'vlan': input_row.vlan(index, input_row.vlan_value),
                'status': 'Active',
                'role': 'n/a',
                'is_pool': '',
                'description': input_row.main_name + ' - ' + input_row.sec_name
            })
    return result


def write_data_file(input_dict, outputfilename, append=False):
    with open(outputfilename, 'a' if append else 'w') as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=input_dict[0].keys(),
            dialect=csv.unix_dialect
        )
        if not append:
            writer.writeheader()
        writer.writerows(input_dict)
        csvfile.flush()
        csvfile.close()


def hex_encode_part(part: int):
    return '{0:0{1}x}'.format(part, 2)


def hex_encode_ip(ip):
    result = ''
    for part in ip.split('.'):
        result += hex_encode_part(int(part))
    return result


def hex_encode_option_43(ips: list):
    no_of_ips = len(ips)
    prefix = '0xf1' + hex_encode_part((no_of_ips * 4))
    ip_encoded_suffix = ''
    for ip in ips:
        ip_encoded_suffix += hex_encode_ip(ip)
    return prefix + ip_encoded_suffix


def getoptions(row, ip):
    result = [
        {
            "name": "routers",
            "data": str(ip[1])
        }
    ]
    if row['vlan_group'] == 'wireless-ap-mgmt':
        result.append({
            "space": "custom-cisco-ap-space",
            "csv-format": False,
            "name": "vendor-encapsulated-options",
            "code": 43,
            "data": hex_encode_option_43([wlan_controller_ip])
        }
    )
    return result


def subnet(row):
    ip = ipaddress.IPv4Network(row['prefix'])

    if ip.prefixlen > 24:
        return

    pool_start = default_pool_start

    return {
        "subnet": ip.with_prefixlen,
        "pools": [
            {
                "pool": str(ip[pool_start]) + "-" + str(ip[pow(2, (32 - ip.prefixlen)) - 6])
            }
        ],
        "relay": {
            "ip-address": str(ip[1])
        },
        "option-data": getoptions(row, ip)
    }


for i, config_file_name in enumerate(config_file_names):
    config_file_name = pathlib.Path(os.path.dirname(__file__), config_file_name)
    if not config_file_name.exists() or not config_file_name.is_file():
        raise FileNotFoundError(config_file_name)
    else:
        config_dict = read_yaml_as_dict(config_file_name, wireless=(i > 0))
        post_config = map_pre_to_post_config(config_dict)
        write_data_file(post_config, data_file_name, (i > 0))

datafile = pathlib.Path(os.path.dirname(__file__), data_file_name)
if not datafile.exists() or not datafile.is_file():
    raise FileNotFoundError(data_file_name)
else:
    data = datafile.read_bytes()

reader = csv.DictReader(io.StringIO(data.decode()), delimiter=',', dialect=csv.unix_dialect)
print('"subnet4":')
print(
    json.dumps(
        list(filter(None, (subnet(row) for row in reader))),
        indent=True
    )
)
