#!/usr/bin/env python3
"""Quick test of SNMP discovery with asyncio"""

import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

async def test_snmp(ip, community='abayonet'):
    """Test SNMP interface discovery"""
    print(f"Testing SNMP on {ip} with community '{community}'...")
    
    snmpEngine = SnmpEngine()
    
    # Try a simple GET first
    errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
        snmpEngine,
        CommunityData(community),
        await UdpTransportTarget.create((ip, 161)),
        ContextData(),
        ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysDescr', 0))
    )
    
    if errorIndication:
        print(f"ERROR: {errorIndication}")
        return
    
    if errorStatus:
        print(f"ERROR: {errorStatus.prettyPrint()}")
        return
    
    for varBind in varBinds:
        print(f"Success: {' = '.join([x.prettyPrint() for x in varBind])}")
    
    # Now try walking interfaces
    print("\nWalking interfaces...")
    varBinds = [ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.2'))]  # ifDescr
    
    errorIndication, errorStatus, errorIndex, varBindTable = await next_cmd(
        snmpEngine,
        CommunityData(community),
        await UdpTransportTarget.create((ip, 161)),
        ContextData(),
        *varBinds
    )
    
    if errorIndication:
        print(f"ERROR: {errorIndication}")
        return
    
    if errorStatus:
        print(f"ERROR: {errorStatus.prettyPrint()}")
        return
    
    print(f"Found {len(varBindTable)} interfaces:")
    for varBind in varBindTable:
        print(f"  {' = '.join([x.prettyPrint() for x in varBind])}")

if __name__ == '__main__':
    asyncio.run(test_snmp('197.234.39.74', 'abayonet'))
