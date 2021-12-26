# usb-watchdog

This project is largley based off of ```Progman2K's``` repo https://github.com/Progman2k/USB_Watchdog   
and supports the following (HID) usb-watchdog device:  

```lsusb``` output:  
```ID 5131:2007 MSR MSR-101U Mini HID magnetic card reader```

It's confusing as there seems to be many devices like this on the market using the same ```5131:2007``` id. 

The main difference between this device and ```Progman2K's``` device and that this device doesn't have an integrated power button, also the command format is different.

This device accepts the following commands comprised of two bytes:  
**ping/hearbeat:** ['0x1e', '0x00']  
**restart:** ['0xff', '0x55']

If the device doesn't receive a ping/heartbeat message within a ```5 minute / 300 second``` period, the relays will be triggered, causing the system to reboot.   
After a ping/heartbeat is sent to the usb watchdog device, a read operation is performed to confirm that the device recieved the command.  
If these values differ, an error message will be displayed:
```
WARNING  Watchdog's TX and RX don't match
TX 0x1e00
RX 0x0eff
```

This script requires the ```pyusb``` and ```systemd-python``` python libraries to run.  
You can install it via your distro's package management tool or via pip3

**fedora package install**  
```dnf install python3-pyusb python3-systemd```

**pip package install**  
```pip3 install systemd-python pyusb```

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
  --date                Output date/time with each logging entry
  --systemd             Use the systemd/journald logging mechanism
  -u USBVENDOR, --usbvendor USBVENDOR
                        usb vendor id, default value: 5131
  -p USBPRODUCT, --usbproduct USBPRODUCT
                        usb product id, default value: 2007
```

You can physically verify whether the ping/heartbeart messages are being received correctly by the usb-watchdog device.  
Each time the device successfully receives a ping/heartbeat message, the blue led on the device will blink.


**setup the usb_watchdog service**  
```
git clone https://github.com/leifliddy/usb-watchdog.git
cd usb-watchdog

sudo cp usb_watchdog.py /usr/local/sbin/
sudo cp usb_watchdog.service /etc/systemd/system/
systemctl enable --now usb_watchdog.service
```

running ```journalctl -f``` will show you the ping intervals
```
Dec 24 06:31:01 black.example.com usb_watchdog[117201]: pinging!
Dec 24 06:31:11 black.example.com usb_watchdog[117201]: pinging!
Dec 24 06:31:21 black.example.com usb_watchdog[117201]: pinging!
Dec 24 06:31:31 black.example.com usb_watchdog[117201]: pinging!
Dec 24 06:31:41 black.example.com usb_watchdog[117201]: pinging!
```

Also, you can start the ```usb_watchdog``` service without needing the usb-watchdog device to be plugged in.  
If/when the device is plugged in at a later time, the service will identify, connect, and start communicating with it.
