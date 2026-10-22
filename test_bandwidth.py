#!/usr/bin/env python3
"""Test SNMP bandwidth counter retrieval"""
import sys
import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

async def get_bandwidth(ip, if_index, community='public'):
    """Get bandwidth counters for an interface"""
    try:
        snmpEngine = SnmpEngine()
        transport = await UdpTransportTarget.create((ip, 161), timeout=5, retries=1)
        
        OID_ifInOctets = f'1.3.6.1.2.1.2.2.1.10.{if_index}'
        OID_ifOutOctets = f'1.3.6.1.2.1.2.2.1.16.{if_index}'
        
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmpEngine,
            CommunityData(community),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(OID_ifInOctets)),
            ObjectType(ObjectIdentity(OID_ifOutOctets))
        )
        
        if errorIndication:
            print(f"Error: {errorIndication}")
            return None
        
        if errorStatus:
            print(f"Error: {errorStatus.prettyPrint()}")
            return None
        
        in_octets = None
        out_octets = None
        
        for varBind in varBinds:
            oid_str = str(varBind[0])
            if '.10.' in oid_str:
                in_octets = int(varBind[1])
                print(f"ifInOctets: {in_octets:,}")
            elif '.16.' in oid_str:
                out_octets = int(varBind[1])
                print(f"ifOutOctets: {out_octets:,}")
        
        return {'in_octets': in_octets, 'out_octets': out_octets}
    
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: ./test_bandwidth.py <ip> <if_index> [community]")
        print("Example: ./test_bandwidth.py 197.234.48.142 2 abayonet")
        sys.exit(1)
    
    ip = sys.argv[1]
    if_index = int(sys.argv[2])
    community = sys.argv[3] if len(sys.argv) > 3 else 'public'
    
    print(f"Getting bandwidth counters for {ip} interface {if_index}...")
    result = asyncio.run(get_bandwidth(ip, if_index, community))
    
    if result:
        print(f"\n✅ Success!")
        print(f"In:  {result['in_octets']:,} octets")
        print(f"Out: {result['out_octets']:,} octets")
    else:
        print("\n❌ Failed to get bandwidth counters")
