#!/usr/bin/env python3
"""Quick test of SNMP discovery"""

from pysnmp.entity.rfc3413 import cmdgen

def test_snmp(ip, community='abayonet'):
    """Test SNMP interface discovery"""
    print(f"Testing SNMP on {ip} with community '{community}'...")
    
    cmdGen = cmdgen.CommandGenerator()
    comm_data = cmdgen.CommunityData('agent', community, 0)
    transport = cmdgen.UdpTransportTarget((ip, 161), timeout=5, retries=1)
    
    OID_ifDescr = '1.3.6.1.2.1.2.2.1.2'
    
    print(f"Walking OID {OID_ifDescr}...")
    errorIndication, errorStatus, errorIndex, varBindTable = cmdGen.nextCmd(
        comm_data, transport, OID_ifDescr
    )
    
    if errorIndication:
        print(f"ERROR: {errorIndication}")
        return
    
    if errorStatus:
        print(f"ERROR: {errorStatus.prettyPrint()} at {errorIndex}")
        return
    
    print(f"Success! Found {len(varBindTable)} interface(s):")
    for varBindTableRow in varBindTable:
        for name, val in varBindTableRow:
            oid_str = str(name)
            if_index = oid_str.split('.')[-1]
            print(f"  Interface {if_index}: {val}")

if __name__ == '__main__':
    test_snmp('197.234.39.74', 'abayonet')
