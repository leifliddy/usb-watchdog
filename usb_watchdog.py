#!/usr/bin/python3

import argparse
import configparser
import errno
import logging
import os
import sys
import usb.core
import usb.util
import time
from datetime import datetime


def FatalError(message=None):
    """ This displays a text message and forces the program to exit with an error. """
    felogger = logging.getLogger('FatalError')
    # Wrapping this in a 'try' to silence any exceptions we trigger here.
    # This is part of silently quitting when we trap CTRL+C
    try:            #print('epinxxxx\n', epin.bEndpointAddress)
        if message:
            # I prefer this format on screen.
            print('\nFATAL ERROR: ' + message, file=sys.stderr)
            # Now ensure the console streamhandler will reject this
            # by setting its level too high.
            logging.getLogger().handlers[0].setLevel(logging.CRITICAL)
            felogger.error(message)
        else:
            # Not blocking the console text here, because I consider
            # an undefined issue to be a big issue.
            felogger.error('No descriptive text provided')
        usbcleanup()
    except:
        pass
    sys.exit(1)

#############################################################################

# From https://www.pythoncentral.io/how-to-implement-an-enum-in-python/
def enum(*args):
    # Used to declare an 'enum' dynamically
    enums = dict(zip(args, range(len(args))))
    return type('Enum', (), enums)

#############################################################################

def get_date():
    # format: Dec 20 07:38:10
    date = datetime.today().strftime('%b %d %H:%M:%S')
    
    return date

#############################################################################

def SendAndReceive(ep_out, ep_in, dout):
    # Send a packet and return the USB device's reply as a string
    logging.debug('TX  0x' + str(dout.hex()))
    ep_out.write(dout)
    data_read = ep_in.read(ep_in.bEndpointAddress, 16)
    din = ''.join('%02x' %i for i in data_read)
    logging.debug('RX  0x' + din + '\n')

    return din

#############################################################################

def SendAndCompare(ep_out, ep_in, dout):
    # Send a packet and expect the USB device to reply with the same packet.
    # If the reply differs that usually seems to indicate a problem.
    
    din_hex = SendAndReceive(ep_out, ep_in, dout)
    dout_hex = dout.hex()

    if dout_hex != din_hex:
      logging.warning("Watchdog's TX and RX don't match\nTX 0x" + dout_hex + '\nRX 0x' + din_hex + '\n')
    return dout_hex == din_hex

#############################################################################

def DrainUSB(ep_in):
    # Read and discard anything waiting at the USB device.
    # Setting a short timep_out period so we don't waste time.
    # Stopping at 256 reads just to prevent infinite loops.
    logging.debug('Trying to drain USB device input buffer')
    try:
        for i in range(0,256):
            tmp = ep_in.read(1024,10)
            logging.debug('Drained ' + len(tmp) + ' bytes from USB endpoint')
    except usb.USBError:
        logging.debug('Finished attempts to drain')
        pass

#############################################################################   

def usbinit(usb_vendor_id, usb_prodcut_id, quiet=False):
    # Convert usb_vendor_id and usb_prodcut_id hex string to integers

    if isinstance(usb_vendor_id, str):    
        usb_vendor_id = int(usb_vendor_id,16)
    if isinstance(usb_prodcut_id, str):            
        usb_prodcut_id = int(usb_prodcut_id,16)
    logging.debug('Looking for device with idVendor ' + hex(usb_vendor_id) + ', idProduct ' + hex(usb_prodcut_id))
    dev = usb.core.find(idVendor=usb_vendor_id,idProduct=usb_prodcut_id)

    if dev is None:
        raise usb.USBError('Device not found')
    else:
        # We use 'repr(dev)' to get just the ID and bus info rather than
        # the full details that str(dev) would output.
        logging.debug('Watchdog module found: '+repr(dev))

    reattach = False
    try:
        if dev.is_kernel_driver_active(0):
            reattach = True
            logging.debug('Detaching kernel driver')
            dev.detach_kernel_driver(0)
        else:
            logging.debug('Device not claimed by a kernel driver')
    except NotImplementedError:
        # Windows systems may not have a driver that claims it by default
        # Linux systems seem to attach the HID driver as a last resort
        pass

    #dev.reset()
    #time.sleep(0.5)

    # Assume it only has a single 'configuration' and enable it
    dev.set_configuration()
    cfg = dev.get_active_configuration()

    # Get an endpoint instance
    cfg = dev.get_active_configuration()
    intf = cfg[(0,0)]

    ep_out = usb.util.find_descriptor(
        intf,
        # match the first OUT endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)

    ep_in = usb.util.find_descriptor(
        intf,
        # match the first IN endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)

    assert ep_out is not None
    assert ep_in is not None

    # Read from the USB device until its buffer is empty.
    # I have no idea if this is actually needed or not.
    DrainUSB(ep_in)
    return dev, ep_out, ep_in

#############################################################################   

def usbcleanup():
    # Clean up as best we can, ignoring _all_ errors but honoring Ctrl+C
    # (Keyboard Interrupt).  Uses the global 'dev'
    global dev
    try:
        if dev != None:
            usb.util.dispose_resources(dev)
    except KeyboardInterrupt:
        raise
    except:
        pass
    time.sleep(0.1)
    try:
        if dev != None:
            dev.reset()
    except KeyboardInterrupt:
        raise
    except:
        pass

#############################################################################
# Begin main code 
#############################################################################

def main():
    # We'll be referencing the existing globally-defined 'dev' variable
    global dev

    cfgusb_vendor_id  = '0x5131'
    cfgusb_prodcut_id = '0x2007'
    #ping       = b'\x1e\x00'
    #restart    = b'\xff\x55'
    ping_hex    = ['0x1e', '0x00']
    ping        = bytes([int(x,0) for x in ping_hex])
    restart_hex = ['0xff', '0x55']
    restart     = bytes([int(x,0) for x in restart_hex])

    config = configparser.ConfigParser()

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False)

    parser.add_argument('-h','--help', action='help', help='Show this help message and exit')
    parser.add_argument('-i', '--interval',  action='store', type=int, default=10, help='Watchdog ping interval in seconds (must be between 1 and 299)')    
    parser.add_argument('-q','--quiet', action='store_true', help='Silences all output')
    parser.add_argument('-r','--restart', action='store_true', help='Restart system via the watchdog USB device')
    parser.add_argument('-d','--debug', action='store_true', help='Output verbose debugging information')
    parser.add_argument('-u', '--usbvendor', action='store', type=str, default=cfgusb_vendor_id, help='USB Vendor ID like 5131')
    parser.add_argument('-p', '--usbproduct', action='store', type=str, default=cfgusb_prodcut_id, help='USB Product ID like 2007')
    args = parser.parse_args()


    if not 1 <= args.interval <= 299:
       print('The interval specified {} is not between 1 and 299'.format(args.interval))
       print('exiting...')
       sys.exit(1)

    if args.usbvendor:
        usb_vendor_id = hex(int(args.usbvendor, 16))

    if args.usbproduct:
        usb_product_id = hex(int(args.usbproduct, 16))
    # Logging hierarchy, for reference
    #   CRITICAL   50
    #   ERROR      40
    #   WARNING    30
    #   INFO       20
    #   DEBUG      10
    #   NOTSET      0
    # We set the logger object to accept Info and above only...
    # (Old format string: '%(name)-8s %(levelname)-8s %(message)s' )
    logging.basicConfig(format='%(levelname)-8s %(message)s',level=logging.INFO)
    # ...then we set its auto-created StreamHandler to Debug and above only.
    logging.getLogger().handlers[0].setLevel(logging.DEBUG)
    # This has the effect of making the logger accept everything but debug by
    # default, but will allow on-screen debug output if enabled later.


    if args.quiet:
        # Setting this to a value never used in the program
        logging.getLogger().setLevel(logging.CRITICAL)

    if args.debug:
        # Enable Debug level (and up) at the root logger
        logging.getLogger().setLevel(logging.DEBUG)

    State = enum('STARTUP', 'DISCONNECTED', 'CONNECTED')
    laststatus=State.STARTUP
    dev = None
    while True:
        try:
            dev, ep_out, ep_in = usbinit(args.usbvendor, args.usbproduct, quiet=args.quiet)
            laststatus=State.CONNECTED

            logging.debug('usb_vendor_id: ' + usb_vendor_id)
            logging.debug('usb_product_id: ' + usb_product_id + '\n')
            logging.debug('ep_out\n' + str(ep_out) + '\n')
            logging.debug('ep_in\n' + str(ep_in) + '\n')
            #print('epinxxxx\n', epin.bEndpointAddress)
            while True:
                if args.restart:
                    logging.info('Restarting system...')    
                    SendAndCompare(ep_out, ep_in, restart)
                    sys.exit()

                if not args.quiet:
                    date = get_date()
                    logging.info(date + ': Pinging!')
                    #print(date + ': Pinging!')
            
                SendAndCompare(ep_out, ep_in, ping)

                time.sleep(args.interval)
        except ValueError as e:
            logging.debug('Encountered ValueError:\n'+repr(e)+'\n')
        except usb.USBError as e:
            etype, evalue, etraceback = sys.exc_info()
            #logging.debug('USBError:\n  type: ' + str(etype) + '\n  value: ' + str(evalue) + '\n  traceback: ' + str(etraceback))
            if evalue.errno == errno.EACCES:
                logging.error('Insufficient permissions to access the device.\nThis is an OS problem you must correct.')
            # Don't bother showing an error if we were still initializing
            if laststatus == State.CONNECTED:
                logging.error('USB communication error or device removed.')
                logging.debug('Encountered USBError:\n'+repr(e)+'\n')
        # Clean up as best we can and try again
        usbcleanup()
        # If our first effort to find the module failed we should give
        # some indication that we are, in fact, trying.
        if laststatus == State.STARTUP:
            logging.info('Waiting for watchdog module to be connected...')
        laststatus=State.DISCONNECTED
        time.sleep(2)


    # Test a range of inputs and show the reply from the module
    #print('Dec\tHex\tReply\tBinary')
    #for x in range(126,256):
        #ret=SendAndReceive(epout, epin, chr(x))
        #rethex=toHex(ret)
        #retbin=bin(int(rethex,16))[2:].zfill(16)
        #print(str(x)+'\t'+hex(x)[:4]+'\t0x'+rethex[:4])
        ##print(str(x)+'\t'+hex(x)+'\t0x'+rethex+'\t'+str(retbin))
        #time.sleep(0.2)

    logging.info('Closing down')

#############################################################################

if __name__ == '__main__':
    try:
        # In order to help with cleanup of USB connections when quitting,
        # we are going to store the USB device reference as a global.
        # Here we simply declare it with no value.
        dev = None
        main()
    except KeyboardInterrupt:
        print('\n')
        FatalError('User pressed CTRL+C, aborting...')
    #except Exception as e:
        #FatalError('Exception: ' + repr(e))
