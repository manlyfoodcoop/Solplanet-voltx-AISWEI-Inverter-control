# Solplanet-voltx-AISWEI-Inverter-control
Sample python code you can use / copy into your own projects to read and control the inverter / battery (DISCHARGE, CHARGE, HOLD). I use this in Sydney against my electricty provider (Amber) who offer the wholesale rate, so I basically code CHARGES and DISCHARGES based on the battery "state of charge", cost price / feed in price, time of day, predicted evening peak. At this stage I have only uploaded basic control code as I actually found this to be the hardest part of the project! Also callout to https://github.com/matus-markusek/homeassistant-solplanet who offer a great home assistant integration (which might suit more people), but code below might suit people who want to code outside of the Home Assistant eco system...

** Don't forget to set your inverter app to "Custom mode" (rather than say "self-consumption mode") as this solution utilises the Custom scheduling capability which will be ignored by the system if you are in a different mode. This also means any custom mode schedules you enter will be overwritten (although you could code for this to preserve existing manually entered entries by reading them first and writing them back) **

__________________________________________
To see if this code is going to work against your inverter, run the curl commands below to see if you get anything back:

* First find the IP address of your inverter. Mine did not show up on my router list, so I ended up using a network scanner tool to find it (trial and error, using curl commands below). Once I found it I made it a static IP address using the DHCP options on my router so I can then hard code the address in my code

* Next get the serial number of your inverter (as this is used as a basic security on some of the calls). Mine looked like AL010K5SQ25CXXX and was visible in the phone app and also on a sticker on the side of the inverter (NOT the dongle!)

* Now try this command (this example gets power settings)
  
  **curl "https://192.168.XXX.XXX:443/getdevdata.cgi?device=2&sn=AL010K5SQ25CXXX" --insecure**
  
  should come back with some data:
  {"flg":1,"tim":"20260311110812","tmp":491,"fac":4995,"pac":164,"sac":219,"qac":145,"eto":-497,"etd":-86,"hto":157,"pf":75,"err":0,"vac":[2463],"iac":[7],"vpv":[0,0,0],"ipv":[0,0,0],"str":[],"stu":1,"pac1":-1,"qac1":-1,"pac2":-1,"qac2":-1,"pac3":-1,"qac3":-1,"grid_sts":1}

* Also this command (this get the current schedule, which can be manipulated / scripted to provide control over the battery

    **curl "https://192.168.XXX.XXX:443/getdefine.cgi" --insecure**

  should return current schedule data:
    {"Pin":8000,"Pout":8000,"Sun":[0,0,0,0,0,0],"Mon":[0,0,0,0,0,0],"Tus":[0,0,0,0,0,0],"Wen":[184580098,0,0,0,0,0],"Thu":[0,0,0,0,0,0],"Fri":[0,0,0,0,0,0],"Sat":[0,0,0,0,0,0]}

If you get those commands working, the you should be able to use the python sample scripts!

** NOTE: Scripts are provided as-is. Not sure if it voids any warranty or anything, but basically (as far as I can tell) these scripts use the same mechanisms as the mobile app (although the mobile app seems to route the commands via cloud). Still, in your code, maybe a good idea not the thrash between charge / discharge at high frequency!

Magennis Weate
magennis.weate@gmail.com
