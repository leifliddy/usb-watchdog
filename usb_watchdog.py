#!/usr/bin/python3

import argparse
import configparser
import errno
import logging
import os
import sys
import time
import usb.core
import usb.util
from datetime import datetime
from systemd import journal


def fatal_error(message=None):
    """ This displays a text message and forces the program to exit with an error. """
    felogger = logging.getLogger('FatalError')
    # Wrapping this in a 'try' to silence any exceptions we trigger here.
    # This is part of silently quitting when we trap CTRL+C
    try:
        if message:
            # I prefer this format on screen.
            print(f'\nFATAL ERROR: {message}', file=sys.stderr)
            # Now ensure the console streamhandler will reject this
            # by setting its level too high.
            logging.getLogger().handlers[0].setLevel(logging.CRITICAL)
            felogger.error(message)
        else:
            # Not blocking the console text here, because I consider
            # an undefined issue to be a big issue.
            felogger.error('No descriptive text provided')
        usb_cleanup()
    except:
        pass
    sys.exit(1)

#############################################################################

def enum(*args):
    # Used to declare an 'enum' dynamically
    enums = dict(zip(args, range(len(args))))
    return type('Enum', (), enums)

#############################################################################

def send_and_receive(ep_out, ep_in, dout):
    # Send a packet and return the USB device's reply as a string
    logging.debug(f'TX  0x{str(dout.hex())}')
    ep_out.write(dout)
    data_read = ep_in.read(ep_in.bEndpointAddress, 16)
    din = ''.join('%02x' %i for i in data_read)
    logging.debug(f'RX  0x{din}\n')

    return din

#############################################################################

def send_and_compare(ep_out, ep_in, dout):
    # Send a packet and expect the USB device to reply with the same packet.
    # If the reply differs that usually seems to indicate a problem.

    din_hex = send_and_receive(ep_out, ep_in, dout)
    dout_hex = dout.hex()

    if dout_hex != din_hex:
      logging.warning(f"Watchdog's TX and RX don't match\nTX 0x{dout_hex}\nRX 0x{din_hex}\n")
    return dout_hex == din_hex

#############################################################################

def drain_usb(ep_in):
    # Read and discard anything waiting at the USB device.
    # Setting a short timep_out period so we don't waste time.
    # Stopping at 256 reads just to prevent infinite loops.
    logging.debug('Trying to drain USB device input buffer')
    try:
        for i in range(0,256):
            tmp = ep_in.read(1024,10)
            logging.debug(f'Drained {len(tmp)} bytes from USB endpoint')
    except usb.USBError:
        logging.debug('Finished attempts to drain')
        pass

#############################################################################

def usb_init(usb_vendor_id, usb_product_id, quiet=False):
    # Convert usb_vendor_id and usb_product_id hex string to integers

    if isinstance(usb_vendor_id, str):
        usb_vendor_id = int(usb_vendor_id,16)
    if isinstance(usb_product_id, str):
        usb_product_id = int(usb_product_id,16)
    logging.debug(f'Looking for device with idVendor {hex(usb_vendor_id)}, idProduct {hex(usb_product_id)}')
    dev = usb.core.find(idVendor=usb_vendor_id,idProduct=usb_product_id)

    if dev is None:
        raise usb.USBError('Device not found')
    else:
        # We use 'repr(dev)' to get just the ID and bus info rather than
        # the full details that str(dev) would output.
        logging.debug(f'Watchdog module found: {repr(dev)}')

    reattach = False
    try:
        if dev.is_kernel_driver_active(0):
            reattach = True
            logging.debug('Detaching kernel driver')
            dev.detach_kernel_driver(0)
        else:
            logging.debug('Device not claimed by a kernel driver')
    except NotImplementedError:
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
        # match the first IN endpointexe=
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)

    assert ep_out is not None
    assert ep_in is not None

    # Read from the USB device until its buffer is empty.
    # I have no idea if this is actually needed or not.
    drain_usb(ep_in)
    return dev, ep_out, ep_in

#############################################################################

def usb_cleanup():
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

    usb_vendor_id  = '0x5131'
    usb_product_id = '0x2007'
    #ping       = b'\x1e\x00'
    #restart    = b'\xff\x55'
    ping_hex    = ['0x1e', '0x00']
    ping        = bytes([int(x,0) for x in ping_hex])
    restart_hex = ['0xff', '0x55']
    restart     = bytes([int(x,0) for x in restart_hex])

    config = configparser.ConfigParser()

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False)

    parser.add_argument('-h','--help', action='help', help='Show this help message and exit')
    parser.add_argument('-i', '--interval', action='store', type=int, default=10, help='Watchdog ping interval in seconds, should be under 230, default value: 10')
    parser.add_argument('-q','--quiet', action='store_true', help='silences all output')
    parser.add_argument('-r','--restart', action='store_true', help='send the restart command to the USB watchdog device')
    parser.add_argument('-d','--debug', action='store_true', help='output debug info')
    parser.add_argument('--systemd', action='store_true', help='use the systemd/journald logging mechanism')
    parser.add_argument('-u', '--usbvendor', action='store', type=str, default=usb_vendor_id, help='usb vendor id, default value: 5131')
    parser.add_argument('-p', '--usbproduct', action='store', type=str, default=usb_product_id, help='usb product id, default value: 2007')

    args = parser.parse_args()

    if not 1 <= args.interval <= 229:
       print(f'The interval specified {args.interval} is not between 1 and 229')
       print('exiting...')
       sys.exit(1)

    if args.usbvendor:
        usb_vendor_id = hex(int(args.usbvendor, 16))

    if args.usbproduct:
        usb_product_id = hex(int(args.usbproduct, 16))

    logger = logging.getLogger()

    if args.systemd:
        logger.addHandler(journal.JournalHandler(SYSLOG_IDENTIFIER='usb_watchdog'))
    else:
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        formatter = logging.Formatter('%(levelname)-8s %(asctime)-19s %(message)s', datefmt='%b %d %H:%M:%S') 
        ch.setFormatter(formatter)
        logger.addHandler(ch)


    if args.quiet:
        logger.disabled = True
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)


    State = enum('STARTUP', 'DISCONNECTED', 'CONNECTED')
    laststatus=State.STARTUP
    dev = None
    while True:
        try:
            dev, ep_out, ep_in = usb_init(args.usbvendor, args.usbproduct, quiet=args.quiet)
            laststatus=State.CONNECTED
            logging.debug(f'usb_vendor_id: {usb_vendor_id}')
            logging.debug(f'usb_product_id: {usb_product_id}\n')
            logging.debug(f'ep_out\n{str(ep_out)}\n')
            logging.debug(f'ep_in\n{str(ep_in)}\n')

            while True:
                if args.restart:
                    logging.info('restarting system...')
                    send_and_compare(ep_out, ep_in, restart)
                    sys.exit()

                logging.info('pinging!')
                send_and_compare(ep_out, ep_in, ping)

                time.sleep(args.interval)
        except ValueError as e:
            logging.debug(f'Encountered ValueError:\n{repr(e)}\n')
        except usb.USBError as e:
            etype, evalue, etraceback = sys.exc_info()
            #logging.debug(f'USBError:\n  type: {str(etype)}\n  value: {str(evalue)}\n  traceback: {str(etraceback)}')
            if evalue.errno == errno.EACCES:
                logging.error('Insufficient permissions to access the device.\nThis is an OS problem you must correct.')
            # Don't bother showing an error if we were still initializing
            if laststatus == State.CONNECTED:
                logging.error('USB communication error or device removed.')
                logging.debug(f'Encountered USBError:\n{repr(e)}\n')
        # Clean up as best we can and try again
        usb_cleanup()
        # If our first effort to find the module failed we should give
        # some indication that we are, in fact, trying.
        if laststatus == State.STARTUP:
            logging.info('Waiting for watchdog module to be connected...')
        laststatus=State.DISCONNECTED
        time.sleep(2)

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
        fatal_error('User pressed CTRL+C, aborting...')
    #except Exception as e:
        #fatal_error(f'Exception: {repr(e)})
