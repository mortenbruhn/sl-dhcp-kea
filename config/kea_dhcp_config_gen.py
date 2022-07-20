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
            cidr_subnet
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
        self.indexes = range(1, 9)

    def network(self, value):
        try:
            return str(ipaddress.IPv4Network(value, strict=False))
        except ValueError:
            return ipaddress.IPv4Address(value).exploded + '/' + str(self.cidr_subnet)

    def index_check(self, index):
        return self.indexes.index(index)

    def vrf(self, index):
        self.index_check(index)
        return 'VRF' + str((self.offsets[index - 1] * self.vrf_incr))

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

    def vrf_desc(self, index): pass


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
            24
        )
        self.vrf_descs_in_order = [
            'wireless-ap-mgmt',
            'it-netnisser',
            'STAB',
            'IP Telefoni',
            'Beredskabet',
            'hotspot',
            'Video',
            'Skejser'
        ]

    def vrf_desc(self, index):
        self.index_check(index)
        return self.vrf_descs_in_order[index - 1]


class WirelessConfigRow(ConfigRow):
    def __init__(self, main_name, sec_name, ip_value, vlan_value):
        super().__init__(
            main_name,
            sec_name,
            ip_value,
            vlan_value,
            range(0, 8),
            10,
            10,
            10,
            20
        )

    def vrf_desc(self, index):
        self.index_check(index)
        return 'wifi-client-range'


wired_config_name = 'wired-config.yaml'
wifi_config_name = 'wifi-config.yaml'
config_file_names = [wired_config_name, wifi_config_name]
data_file_name = 'data.csv'
poolstart = 11


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
                            WirelessConfigRow(main_name, sec_name, ip_value, vlan_value)
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
                'vrf': input_row.vrf(index),
                'tenant': 'SL2022',
                'site': 'sl2022',
                'vlan_group': input_row.vrf_desc(index),
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


def subnet(row):
    ip = ipaddress.IPv4Network(row['prefix'])

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


for i, config_file_name in enumerate(config_file_names):
    config_file_name = pathlib.Path(os.path.dirname(__file__), config_file_name)
    if not config_file_name.exists() or not config_file_name.is_file():
        raise FileNotFoundError(config_file_name)
    else:
        config_dict = read_yaml_as_dict(config_file_name)
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
