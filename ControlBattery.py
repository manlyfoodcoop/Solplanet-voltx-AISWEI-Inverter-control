import asyncio 
from datetime import datetime 
from datetime import timedelta, time as dt_time  
import requests
from datetime import datetime
import json
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, asdict
from typing import Any
from enum import Enum
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BatteryMode(Enum):
    CHARGE = 1
    DISCHARGE = 2
    SELF_CONSUMPTION = 3,
    PRESERVE = 4

INVERTER_IP = "192.168.XXX.XXX"  # replace with your inverter's IP address
SERIAL_NUMBER = "AL010K5SQ25C0XXX" # replace with your inverter's serial number

@dataclass
class SetScheduleRequest:
    """Set schedule request."""
    value: dict[str, Any]
    device: int = 4
    action: str = "setdefine"

@dataclass
class ScheduleSlot:
    """Represent a battery schedule time slot."""
    start_hour: int
    start_minute: int
    duration: int
    mode: str

    @classmethod
    def from_raw(cls, code: int) -> 'ScheduleSlot | None':
        """Create slot from raw inverter code."""
        if code == 0:
            return None

        discharge_bit = code & 0x1
        duration_bits = (code >> 14) & 0x3
        half_hour_bit = (code >> 17) & 0x1
        hour_bits = code >> 24

        return cls(
            start_hour=hour_bits,
            start_minute=30 if half_hour_bit else 0,
            duration=duration_bits + 1,
            mode="discharge" if discharge_bit else "charge"
        )

    @classmethod
    def from_time(cls, start: str, duration: int, mode: str) -> 'ScheduleSlot':
        """Create slot from time string (HH:MM), duration and mode."""
        hour, minute = map(int, start.split(':'))
        if minute not in [0, 30]:
            raise ValueError("Minutes must be 0 or 30")
        if not 0 <= hour <= 23:
            raise ValueError("Hour must be between 0 and 23")
        if not 1 <= duration <= 4:
            raise ValueError("Duration must be between 1 and 4 hours")
        if mode not in ["charge", "discharge"]:
            raise ValueError("Mode must be 'charge' or 'discharge'")

        return cls(
            start_hour=hour,
            start_minute=minute,
            duration=duration,
            mode=mode
        )

    @classmethod
    def from_dict(cls, data: dict) -> 'ScheduleSlot':
        """Create slot from dictionary with start, duration, mode."""
        if isinstance(data.get('start'), str):
            return cls.from_time(data['start'], data['duration'], data['mode'])
        return cls(
            start_hour=data['start_hour'],
            start_minute=data['start_minute'],
            duration=data['duration'],
            mode=data['mode']
        )

    def to_raw(self) -> int:
        """Convert slot to raw inverter format."""
        if self.start_minute not in [0, 30]:
            raise ValueError("Minutes must be 0 or 30")

        BASE = 0x3C02
        HOUR = 0x1000000
        HALF = 0x1E0000
        DURATION = 0x3C00

        return (BASE +
                (self.start_hour * HOUR) +
                ((self.start_minute // 30) * HALF) +
                ((self.duration - 1) * DURATION) +
                (1 if self.mode == "discharge" else 0))

    def to_dict(self) -> dict:
        """Convert slot to dictionary format."""
        return {
            "start_hour": self.start_hour,
            "start_minute": self.start_minute,
            "duration": self.duration,
            "mode": self.mode
        }

    def human_readable(self, format: str = "{start} - {end} ({mode})") -> str:
        """Convert slot to human readable string.

        Args:
            format: Format string with {start}, {end}, {mode} placeholders
        """
        end_hour = (self.start_hour + self.duration) % 24
        return format.format(
            start=f"{self.start_hour:02d}:{self.start_minute:02d}",
            end=f"{end_hour:02d}:{self.start_minute:02d}",
            mode=self.mode
        )

    def validate_duration(self) -> None:
        """Validate slot duration doesn't cross midnight."""
        end_hour = self.start_hour + self.duration
        if end_hour > 24:
            raise ValueError(f"Slot ending at {end_hour}:00 crosses midnight. At {self.start_hour}:00 max duration is {24-self.start_hour} hours")

    @staticmethod
    def validate_slots(slots: list['ScheduleSlot']) -> None:
        """Validate a list of slots."""
        if len(slots) > 6:
            raise ValueError("Maximum 6 slots per day allowed")

        sorted_slots = sorted(slots, key=lambda x: (x.start_hour, x.start_minute))

        for i, slot in enumerate(sorted_slots):
            slot.validate_duration()

            if i < len(sorted_slots) - 1:
                next_slot = sorted_slots[i + 1]
                current_end = slot.start_hour + slot.duration
                current_end_mins = slot.start_minute
                next_start = next_slot.start_hour
                next_start_mins = next_slot.start_minute

                if (current_end > next_start) or (current_end == next_start and current_end_mins > next_start_mins):
                    raise ValueError(f"Slot {slot.human_readable()} overlaps with {next_slot.human_readable()}")


class BatterySchedule:
    """Helper for battery schedule operations."""
    DAYS = ["Mon", "Tus", "Wen", "Thu", "Fri", "Sat", "Sun"]

    @staticmethod
    def decode_schedule(raw_schedule: dict) -> dict[str, list[ScheduleSlot]]:
        """Decode raw schedule into slots."""

        #print(f"Decoding raw schedule: {raw_schedule}")

        decoded = {}

        for day in BatterySchedule.DAYS:
            #print(f"\nProcessing day: {day}")

            slots = []

            # get the raw list for this day
            day_values = raw_schedule.get(day, [])
            

            # limit to first 6 entries
            day_values = day_values[:6]

            for code in day_values:
                

                slot = ScheduleSlot.from_raw(code)

                #if (slot is not None):
                    #print(f"  Decoded slot: {slot}")

                if slot is not None:
                    slots.append(slot)
                    
                    

            decoded[day] = slots
            #print(f"Finished {day}, slots: {slots}")

        return decoded

    @staticmethod
    def encode_schedule(slots: dict[str, list[ScheduleSlot]], pin: int = 5000, pout: int = 5000) -> dict:
        """Encode slots into raw schedule."""
        # Validate slots for each day
        for day_slots in slots.values():
            if day_slots:  # Only validate if there are slots
                ScheduleSlot.validate_slots(day_slots)

        return {
            **{
                day: [slot.to_raw() for slot in day_slots]
                for day, day_slots in slots.items()
                if day_slots  # Only include days with slots
            },
            "Pin": pin,
            "Pout": pout
        }



def get_empty_schedule():
    PL = '{"device":4,"action":"setdefine","value":{"Pin":1234,"Pout":1234,"Sun":[0,0,0,0,0,0],"Mon":[0,0,0,0,0,0],"Tus":[0,0,0,0,0,0],"Wen":[0,0,0,0,0,0],"Thu":[0,0,0,0,0,0],"Fri":[0,0,0,0,0,0],"Sat":[0,0,0,0,0,0]}}'
    J = json.loads(PL)
    slots = BatterySchedule.decode_schedule(J)

    return {
        "raw": PL,       # Store raw API response as-is
        "slots": slots,            # Store decoded schedule
        "Pin": 5000,
        "Pout": 5000
    }


async def get_schedule():
    """Get battery schedule configuration."""
    url = f"https://{INVERTER_IP}:443/getdefine.cgi?device=2&sn={SERIAL_NUMBER}"
    if await MakeGetCall(url,90,None):
        print(f"Raw schedule response: {URLPayLoad}")
        if (URLPayLoad != None and URLPayLoad.startswith('{')):
            J = json.loads(URLPayLoad)
            slots = BatterySchedule.decode_schedule(J)

            return {
                "raw": J,       # Store raw API response as-is
                "slots": slots,            # Store decoded schedule
                "Pin": J.get("Pin", 5000),
                "Pout": J.get("Pout", 5000)
            }
        else:
            await log("Invalid schedule response received")
            return None
    else:
        await log("Failed to retrieve schedule")
        return None
    

def FormatSchedule(schedule: dict) -> str:
    days = ["Sun", "Mon", "Tus", "Wen", "Thu", "Fri", "Sat"]

    value = {}

    # Copy Pin/Pout
    value["Pin"] = schedule.get("Pin", 0)
    value["Pout"] = schedule.get("Pout", 0)

    # Ensure every day exists and has 6 values
    for day in days:
        vals = schedule.get(day, [])
        vals = vals[:6]  # max 6
        vals = vals + [0] * (6 - len(vals))  # pad with zeros
        value[day] = vals

    result = {
        "device": 4,
        "action": "setdefine",
        "value": value
    }

    return json.dumps(result, separators=(",", ":"))

def GetSolPlanetDOW():
    #get day of week as 3 letter string
    dow = datetime.now().strftime("%a")
    if dow == "Mon":
        return "Mon"
    elif dow == "Tue":
        return "Tus"
    elif dow == "Wed":
        return "Wen"
    elif dow == "Thu":
        return "Thu"
    elif dow == "Fri":
        return "Fri"
    elif dow == "Sat":
        return "Sat"
    elif dow == "Sun":
        return "Sun"
    else:
        return None

async def SetBatteryControl(BM, Rate=8000, Hours=1):

    await log(f"Setting SolPlanet charger mode: Charge={BM}, Rate={Rate}, Hours={Hours}")

    try:
        #adjust hours so it does not cross midnight
        now = datetime.now()
        end_time = now + timedelta(hours=Hours)
        if end_time.day != now.day:
            Hours = 24 - now.hour
            await log(f"Adjusted charge hours to avoid crossing midnight: {Hours} hours")

        current = get_empty_schedule()
        if (current is not None):

            if (BM == BatteryMode.CHARGE or BM == BatteryMode.DISCHARGE):
                current["slots"][GetSolPlanetDOW()] = [ScheduleSlot(start_hour=datetime.now().hour, start_minute=0, duration=Hours, mode="charge" if BM == BatteryMode.CHARGE else "discharge")]
            elif (BM == BatteryMode.PRESERVE): #set very low charge rate, as this emulates a preserve state
                current["slots"][GetSolPlanetDOW()] = [ScheduleSlot(start_hour=datetime.now().hour, start_minute=0, duration=Hours, mode="charge")]
                Rate=10
            else:
                Rate=9000

            battery_rate = Rate
            #now encode the schedule, and post it back
            schedule = BatterySchedule.encode_schedule(
                    current["slots"],
                pin=Rate,
                pout=Rate)
            
            scheduleS = FormatSchedule(schedule)
            print(f"Formatted schedule to set: {scheduleS}")
            url = f"https://{INVERTER_IP}:443/setting.cgi"
            await MakeSolPlanetPOSTCall(url, str(scheduleS))
            print("Resp: " + URLPayLoad)

            if (URLPayLoad != '{"dat":"ok"}'):
                await log("Error setting SolPlanet schedule: " + str(URLPayLoad))
                return False
            else:
                return True
        else:
            return False
    except Exception as e:
        await log(f"Exception in SetBatteryControl: {str(e)}")
        return False    




async def MakeSolPlanetPOSTCall(url, string_data):
    global URLPayLoad
    
    URLPayLoad=None
    await log("Attempting SolPlanet POST call: " + url + " - " + string_data)
    try:
        #headers = {"Content-Type": "application/x-www-form-urlencoded"}
        headers = {'Content-Type': 'text/plain'}
        
        response = requests.post(url, data=string_data, headers=headers,   verify=False, timeout=90)
        response.raise_for_status()  # Raise an exception for 4xx and 5xx HTTP status codes if any

        if response.status_code == 200:
            await log(response.text)
            URLPayLoad=response.text
            return True

    except requests.exceptions.RequestException as e:
        await log(f"HTTP Request Error: {e}")
        return False
 

async def log(message):
    timestamp = datetime.now().strftime('%d%m%y - %H:%M:%S')
    formatted_message = f"{timestamp} - {message}"
    print(formatted_message)



async def main():
    if await SetBatteryControl(BatteryMode.CHARGE, 2000, 2)==True:
        print("** Battery control set successfully! **")

  

if __name__ == "__main__":
    asyncio.run(main())

