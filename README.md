# usb-watchdog

This project is largley based off of ```Progman2K's``` repo https://github.com/Progman2k/USB_Watchdog   
and supports the following (HID) usb-watchdog device:  

```ID 5131:2007 MSR MSR-101U Mini HID magnetic card reader```

It's confusing as there seems to be many devices like this on the market using the same ```5131:2007``` id. 

The main difference between this device and ```Progman2K's``` device is the command format 

This device accepts commands comprised of two bytes:  
**ping or hearbeat:** ['0x1e', '0x00']  
**restart:** ['0xff', '0x55']

If the device doesn't receive a ping/heartbeat message within a ```5 minute / 300 second``` period, the relays will be triggered, causing the system to reboot. 


This script requiress the ```pyusb``` python library to run. 
You can install it via your distro's package management tool or via pip3

**fedora package install**  
```dnf install python3-pyusb```

**pip package install**  
```pip3 install pyusb```

**command options**  
Should be pretty self-explanatory

```
./usb_watchdog.py --help
usage: usb_watchdog.py [-h] [-i INTERVAL] [-q] [-r] [-d] [-u USBVENDOR] [-p USBPRODUCT]

options:
  -h, --help            Show this help message and exit
  -i INTERVAL, --interval INTERVAL
                        Watchdog ping interval in seconds, needs to be under 300, default value: 10
  -q, --quiet           Silences all output
  -r, --restart         Restart system via the watchdog USB device
  -d, --debug           Output verbose debugging information
  -u USBVENDOR, --usbvendor USBVENDOR
                        usb vendor id, default value: 5131
  -p USBPRODUCT, --usbproduct USBPRODUCT
                        usb product id, default value: 2007
```

You can physically verify whether the ping/heartbeart messages and being received correctly on the device.
Ever time the device successfully receives a ping/heartbeat message, the blue led on the device will blink.
