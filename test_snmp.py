#!/usr/bin/env python3
"""
Quick SNMP discovery test script
Tests if SNMP interface discovery works for a host
"""
import sys
import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

async def discover_interfaces(ip, community='public'):
    """Test SNMP interface discovery"""
    interfaces = {}
    
    try:
        snmpEngine = SnmpEngine()
        transport = await UdpTransportTarget.create((ip, 161), timeout=5, retries=1)
        
        print(f"Discovering interfaces on {ip} with community '{community}'...")
        
        # Walk ifDescr
        OID_ifDescr = ObjectIdentity('1.3.6.1.2.1.2.2.1.2')
        varBinds = [ObjectType(OID_ifDescr)]
        
        while True:
            errorIndication, errorStatus, errorIndex, varBindTable = await next_cmd(
                snmpEngine,
                CommunityData(community),
                transport,
                ContextData(),
                *varBinds
            )
            
            if errorIndication:
                print(f"  Error: {errorIndication}")
                break
            
            if errorStatus:
                print(f"  Walk ended: {errorStatus.prettyPrint()}")
                break
            
            any_valid = False
            for varBind in varBindTable:
                oid_str = str(varBind[0])
                if '1.3.6.1.2.1.2.2.1.2.' in oid_str:
                    try:
                        if_index = int(oid_str.split('.')[-1])
                        if_name = str(varBind[1])
                        interfaces[if_index] = {
                            'if_index': if_index,
                            'if_name': if_name,
                            'if_speed_bps': 0
                        }
                        print(f"  Found: if{if_index} = {if_name}")
                        any_valid = True
                    except (ValueError, IndexError) as e:
                        print(f"  Parse error: {e}")
            
            if not any_valid:
                break
            
            varBinds = varBindTable
        
        print(f"\nDiscovered {len(interfaces)} interfaces")
        
        # Walk ifSpeed
        if interfaces:
            print("\nGetting interface speeds...")
            OID_ifSpeed = ObjectIdentity('1.3.6.1.2.1.2.2.1.5')
            varBinds = [ObjectType(OID_ifSpeed)]
            
            while True:
                errorIndication, errorStatus, errorIndex, varBindTable = await next_cmd(
                    snmpEngine,
                    CommunityData(community),
                    transport,
                    ContextData(),
                    *varBinds
                )
                
                if errorIndication or errorStatus:
                    break
                
                any_valid = False
                for varBind in varBindTable:
                    oid_str = str(varBind[0])
                    if '1.3.6.1.2.1.2.2.1.5.' in oid_str:
                        try:
                            if_index = int(oid_str.split('.')[-1])
                            if if_index in interfaces:
                                interfaces[if_index]['if_speed_bps'] = int(varBind[1])
                                print(f"  if{if_index} speed: {int(varBind[1]):,} bps")
                            any_valid = True
                        except (ValueError, TypeError):
                            pass
                
                if not any_valid:
                    break
                
                varBinds = varBindTable
        
        return list(interfaces.values())
    
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: ./test_snmp.py <ip> [community]")
        print("Example: ./test_snmp.py 197.234.48.142 abayonet")
        sys.exit(1)
    
    ip = sys.argv[1]
    community = sys.argv[2] if len(sys.argv) > 2 else 'public'
    
    result = asyncio.run(discover_interfaces(ip, community))
    
    print(f"\n{'='*60}")
    print(f"Final result: {len(result)} interfaces discovered")
    for iface in result:
        speed_mbps = iface['if_speed_bps'] / 1000000 if iface['if_speed_bps'] else 0
        print(f"  [{iface['if_index']:2d}] {iface['if_name']:20s} - {speed_mbps:8.1f} Mbps")
