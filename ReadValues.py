from tracemalloc import start

import requests
import json
import urllib3
import struct
import asyncio 
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime 
from datetime import timedelta, time as dt_time  
import os
import statistics
import json
from datetime import datetime, timedelta
from systemd.daemon import notify




# Suppress insecure HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Global defines
INVERTER_IP = "192.168.XXX.XXX"  # replace with your inverter's IP address
SERIAL_NUMBER = "AL010K5SQ25C0XXX" # replace with your inverter's serial number
SLAVE_ID = 1


EnphaseURLString = None

# ----- HELPER FUNCTION -----
# CRC16 Modbus function
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc



async def extract_active_pv(json_data):

    
    try:
        #await log(json_data)
        data = json.loads(json_data)
        SOLAR_METER = None
        GRID_METER = None

        for entry in data:
            if entry["eid"] == 704643328:
                SOLAR_METER = entry["activePower"]
            elif entry["eid"] == 704643584:
                GRID_METER = entry["activePower"]

        #await log(f"+++++++++++++++++++++++++ SOLAR: {SOLAR_METER}, GRID_METER: {GRID_METER}")


        grid = GRID_METER/1000
        production = SOLAR_METER;  # working
        print(f"****PV Value: {production} W")
        #consumption = production+grid+battery_kw;
        return production
    except json.JSONDecodeError as e:
        await log(f"JSON decoding error: {e}")
        return 0

            

async def log(message):
    timestamp = datetime.now().strftime('%d%m%y - %H:%M:%S')
    formatted_message = f"{timestamp} - {message}"
    print(formatted_message)




# note these values can fluctuate so I read some samples and return the median. This is slow!
async def read_register(register, samples=10):
    values = []

    for _ in range(samples):
        val = read_register_value(register)
        if val is not None:
            values.append(val)
        else:
            values.append(0)  # Append 0 for failed reads to avoid issues with empty list

        time.sleep(0.1)  # Small delay between reads

    await log("Register samples:"+ str(values))

    if values:
        return statistics.median(values)
    else:
        return None
    
def read_register_value(register):
    addr_bytes = register.to_bytes(2, byteorder='big')
    payload_bytes = bytes([SLAVE_ID, 0x04]) + addr_bytes + bytes([0x00, 0x02])
    crc = crc16(payload_bytes)
    crc_bytes = crc.to_bytes(2, byteorder='little')  # Modbus CRC = little endian
    full_payload = payload_bytes + crc_bytes
    payload_hex = full_payload.hex()

    url = f"https://{INVERTER_IP}/fdbg.cgi"
    try:
        r = requests.post(url, json={"data": payload_hex}, verify=False, timeout=50)
        r.raise_for_status()
        resp_text = r.text.strip()
    #    print(f"Raw response for register {register:03d}: {resp_text}")

        if '"dat":"err"' in resp_text:
            print(f"Register {register:03d} -> ERR")
            return None

        resp = r.json()
        if resp.get("dat") != "ok":
            print(f"Register {register:03d} -> ERR (dat not ok)")
            return None

        data = resp.get("data", "")
        if len(data) < 14:
            print(f"Register {register:03d} -> SHORT DATA")
            return None

        hex_bytes = data[6:14]
        val = struct.unpack(">f", bytes.fromhex(hex_bytes))[0]
        return val

    except Exception as e:
        print(f"Error reading register {register:03d}: {e}")
        return None

async def MakeGetCall(URL, TimeOut, Authorization):
    global URLPayLoad 
    success = False
    URLPayLoad = None
    await log(f"Calling secure GET: '{URL}'")

    session = requests.Session()
    session.verify = False  # Disable SSL certificate verification (similar to setInsecure)

    try:
        response = session.get(URL, timeout=TimeOut, headers={"Authorization": Authorization})
        if response.status_code == 200:
            URLPayLoad = response.text
            success = True
        else:
            await log(f"response: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
       await log(f"Error calling HTTPsGet: {str(e)}")

    finally:
        session.close()

    return success




async def get_soc():
    # Construct the URL with query parameters
    url = f"https://{INVERTER_IP}:443/getdevdata.cgi?device=4&sn={SERIAL_NUMBER}"
    
    # Make the HTTP GET request with the --insecure option equivalent
    response = requests.get(url, verify=False, )  # Disable SSL verification
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()
        
        # Extract the SOC value from the response
        soc_value = data.get('soc')
        
        # Return the SOC value
        return soc_value
    else:
        await log(f"Failed to get data. Status code: {response.status_code}")
        return None

def get_grid_from_ac(data):
    vac = data.get("vac", [0])
    iac = data.get("iac", [0])
    pf  = data.get("pf", 100)

    V = float(vac[0]) / 10      # volts
    I = float(iac[0])            # amps
    PF = float(pf) / 100         # unitless

    grid_power = V * I * PF / 10
    return grid_power
    
async def get_pow():



    # Construct the URL with query parameters
    url = f"https://{INVERTER_IP}:443/getdevdata.cgi?device=2&sn={SERIAL_NUMBER}"
    
    # Make the HTTP GET request with the --insecure option equivalent
    response = requests.get(url, verify=False, timeout=90)  # Disable SSL verification
    grid_value = float(await read_register(52,5) or 0)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()

      
        
        pv_value = 0
        #note: in my setup I use ENPHASE microinverters, so I get the PV production from the Enphase API, not from the Solplanet inverter. If you have a different setup, you might want to adjust this part to get the PV production directly from the inverter if available.
        #so I have not sourced this inthis example. You will need to unt around to get PV values from the curl commands
        #if someone solves this, please share so I can update the code. 


        # Extract the SOC value from the response
        battery_value = float(data.get('pac', 0))
        sac_value = float(data.get('sac', 0))
        #print(f"sac_value: {sac_value}")
        #print(f"grid_value: {get_grid_from_ac(data)}")


        load_value =  battery_value + pv_value + grid_value
        #pv_value = load_value - grid_value - battery_value
        


        # Return the SOC value
        return battery_value, grid_value, load_value, pv_value
    else:
        print(f"Failed to get data. Status code: {response.status_code}")
        return None


async def main():    


    while True:
        soc = await get_soc()
        if soc is not None:
            print('=========================')
            await log(f"State of Charge (SOC): {soc}%")
        else:
            await log("Failed to retrieve SOC value. Using dummy value 42")


        battery_pow, grid_pow, load_value, pv_value = await get_pow()   
        if battery_pow is not None and grid_pow is not None:
            print(f"Battery Power (PAC): {battery_pow} W")
            print(f"Grid Power (REG 52): {grid_pow} W")
            print(f"Load Power (b + pv + grd): {load_value} W")
            print(f"PV Power (to be implemented): {pv_value} W")

            

            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
