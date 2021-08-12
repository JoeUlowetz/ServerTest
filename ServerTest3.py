# ServerTest3.py
#   2021.08.12 Joe Ulowetz, Impossible Objects

# This file allows multiple different clients to talk to server async at the same time
# This file is not so much a test version as the beginning of the implementation of the
# RPi camera functionality for the SWZP printer. At some point this code will be moved
# back into RPi-Camera-Server (or something like that).
#
# This file, ServerTest3.py is run on the RPi:
#       cd ~/PyCharmRemote/ServerTest
#       python3 ServerTest3.py
#
# It currently uses hard-coded IP address (see end of this file); this needs to be changed
# to read the server's assigned IP address.

# Note that the program ClientTest3.py in the ClientTest project is coded to talk with the
# network protocol implemented here. ClientTest3.py runs from the PC and connects to the RPi.

# Note that test_ServerTest3.py, which is currently part of this ServerTest project, is the beginning
# of unit tests for all the camera functionality. It runs from the PC and connects to the RPi also.
# As functionality is added here to ServerTest3.py, tests for that functionality should be added
# to test_ServerTest3.py

import socket
import socketserver
import time
import json
import os

# for RPI especially:
from examine_platen_page import examine_platen_page
from examine_outfeed_page import examine_outfeed_page
from check_platen_punch import check_platen_punch


# This is base version sending simple strings; next step is convert dict to string

BUFFER_SIZE = 2048      # For the moment, assume all messages will fit in one buffer length
DELTA = 100             # allow for overhead in socket buffer when comparing if message is too large
ENCODING = 'ascii'      # use 'ascii' or 'utf-8'

#server = None
server_thread = None


# -----------------------------------------------------------------------------------------------------------
class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
    """
    Besides having the handle() function to receive/respond to network traffic, this class is responsible for
    decoding and validating the request that is received here (needs to be proper JSON, decode to a dictionary,
    and have certain fields present). If the input validates, this calls the "business logic" for the
    camera functionality in the call: parse_net_cmd().
    When that call returns (which it must do very quickly because the client is blocked until we respond to its
    request), this class then encodes the response dictionary back into a byte string that can be sent in a reply
    back to the client.  After this is done, and the handle() method ends, this means the socket connection that
    was established between the client and server is closed. The socket is only open for the duration of the
    handle() method.
    See documentation for the Python library socketserver for more details.
    """
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)

    # Reminder: the main server loop calls server.handle_request(), and that in turn will call handle() here.
    def handle(self):
        originated = 0
        received = round(time.time(),3)

        # ########################################
        # Receive the bytes, which we assume are
        # JSON-encoded string, from the network
        # ########################################
        data_bytes = self.request.recv(BUFFER_SIZE)
        data_str = str(data_bytes, ENCODING)
        if "API_NOP" not in data_str:
            print("{S}: Server working with:", data_str)    # The NOP message is used to write a line on the screen, to help see where unit tests start and end

        # ########################################
        # Convert the JSON-encoded string into an
        # object, which should be a dictionary
        # ########################################
        try:
            input_data_dict = json.loads(data_str)
        except ValueError:
            # Server received something from client that is not valid json
            print("{S}: ERROR Server received a string that is not valid JSON")
            output_data_dict = {
                'NetCmd': "NET_RESPONSE_PROBLEM",
                'API': 'N/A',
                'Camera': 'N/A',
                'ParsingError': True,
                'NetCmdError': False,
                'APIError': False,
                'SizeError': False,
                'ErrorType': "String was not valid JSON",
                'ErrorDetails': "Server received string which is not valid JSON"}
        else:
            # ########################################
            # Make sure the object we received is a
            # dictionary object as expected
            # ########################################
            if type(input_data_dict) is not dict:
                output_data_dict = {
                    'NetCmd': "NET_RESPONSE_PROBLEM",
                    'API': 'N/A',
                    'Camera': 'N/A',
                    'ParsingError': True,
                    'NetCmdError': False,
                    'APIError': False,
                    'SizeError': False,
                    'ErrorType': "Client did not send dictionary",
                    'ErrorDetails': "Server received object which is not a dictionary"}
            else:
                # Make sure the client request contains the minimum expected fields
                problems = ""
                for field in ["NetCmd", "API", "Camera", "TS1"]:
                    if field not in input_data_dict:
                        problems += "Client request missing field: %s\n" % field
                if len(problems) > 0:
                    output_data_dict = {
                        'NetCmd': "NET_RESPONSE_PROBLEM",
                        'API': 'N/A',
                        'Camera': 'N/A',
                        'ParsingError': True,
                        'NetCmdError': False,
                        'APIError': False,
                        'SizeError': False,
                        'Status': "Missing Request field(s)",
                        'ErrorType':"Missing Client field(s)",
                        'ErrorDetails': problems}
                else:
                    originated = input_data_dict["TS1"]
                    # ########################################
                    # Parsing content of the Client request
                    # ########################################
                    output_data_dict = parse_net_cmd(input_data_dict)   # >>>all business logic occurs inside here<<<

                    # debugging: show dictionary we are returning
                    # print("{S}: Server returning response:", output_data_dict)

        finally:    # send out server response (unless size too large for network buffer)
            # misc info
            output_data_dict["TS1"] = originated    # when client sent out request (IF we could read this from msg); PC clock
            output_data_dict["TS2"] = received      # when server received msg from network; RPi clock
            output_data_dict["TS3"] = round(time.time(),3)   # when server sent out response; RPi clock
            if 'Status' not in output_data_dict:
                output_data_dict['Status'] = "[Not Implemented]"
            output_data_dict['Response'] = True

            # ########################################
            # turn dictionary into JSON-encoded string
            # ########################################
            out_string = json.dumps(output_data_dict)       # TODO: could this throw an exception?

            # ########################################
            # convert string to bytes so it can be sent to socket
            # ########################################
            out_bytes = bytes(out_string, ENCODING)

            # make sure we aren't exceeding our expected buffer size limit
            if len(out_bytes) >= (BUFFER_SIZE-DELTA):
                print("{S}: SERVER ERROR: outgoing message too large for network buffer!!!")
                output_data_dict = {
                    'NetCmd': "NET_RESPONSE_PROBLEM",
                    'API': output_data_dict['API'],
                    'Camera': output_data_dict['Camera'],
                    'ParsingError': False,
                    'NetCmdError': False,
                    'APIError': False,
                    'SizeError': True,
                    'ErrorType': "Server response too large",
                    'ErrorDetails': "Return message from server would exceed buffer size of 2K; server generated message = %d bytes" % len(out_bytes),
                }

                out_string = json.dumps(output_data_dict)
                out_bytes = bytes(out_string, ENCODING)
                # Note: truncating buffer makes it invalid JSON, so we just can't truncate
                # our buffer. Instead we return a different message to describe problem



            # print("{S}: --server delay here--")
            # time.sleep(10)     # pretend to do work here...
            # print("{S}: --server continues now--:", out_string)

            # ########################################
            # Send out the server's response to the client request
            # ########################################
            self.request.sendall(out_bytes)

            # Special handling if client requested API_REBOOT
            if 'Reboot' in output_data_dict and output_data_dict['Reboot']:
                print("{S}: Rebooting RPi now!")
                time.sleep(2)   # give network response a chance to reach client
                os.system('sudo shutdown -r now')


# -----------------------------------------------------------------------------------------------------------
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


# -----------------------------------------------------------------------------------------------------------
def parse_net_cmd(input_data_dict):
    # TODO: remember to check for additional required input dict fields, and return error if missing
    net_cmd = input_data_dict["NetCmd"]
    if net_cmd == "NET_REQUEST_IMMEDIATE":
        output_data_dict = net_request_immediate(input_data_dict)
    elif net_cmd == "NET_REQUEST_ACTION":
        output_data_dict = net_request_action(input_data_dict)
    elif net_cmd == "NET_REQUEST_POLL":
        output_data_dict = net_request_poll(input_data_dict)
    elif net_cmd == "NET_REQUEST_ABORT":
        output_data_dict = net_request_abort(input_data_dict)
    else:
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_PROBLEM",
            'API': input_data_dict['API'],
            'Camera': input_data_dict['Camera'],
            'ParsingError': False,
            'NetCmdError': True,
            'APIError': False,
            'SizeError': False,
            'ErrorType': "Invalid NetCmd",
            'ErrorDetails': "Client sent message with invalid NetCmd: %s" % net_cmd}
    return output_data_dict


# -----------------------------------------------------------------------------------------------------------
def net_request_immediate(input_data_dict):
    # This handles:  NET_REQUEST_IMMEDIATE
    # Commands allowed: API_PING, API_START_HARDWARE?, API_STATUS, API_REAR_CONVEYOR?, API_TAKE_PICTURE
    # returns dictionary: output_data_dict
    api_cmd = input_data_dict["API"]

    if api_cmd == "API_PING":
        # just send back response!
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_IMMEDIATE",
            'API': api_cmd,     # == "API_PING"
            'Camera': input_data_dict['Camera'],
            'Status': "OK"
        }
        return output_data_dict

    elif api_cmd == "API_NOP":
        # this is just formatting to help keep track of test start/end
        print("--------------------------------------------------------")
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_IMMEDIATE",
            'API': api_cmd,     # == "API_PING"
            'Camera': input_data_dict['Camera'],
            'Status': "OK"
        }
        return output_data_dict

    elif api_cmd == "API_START_HARDWARE":
        # stuff to do here
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_IMMEDIATE",
            'API': api_cmd,  # == "API_START_HARDWARE"
            'Camera': input_data_dict['Camera'],
            'ErrorType': "Command NOT IMPLEMENTED YET",     # FIX THIS!
        }
        return output_data_dict

    elif api_cmd == "API_START_PRINT_JOB":
        # stuff to do here
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_IMMEDIATE",
            'API': api_cmd,  # == "API_START_PRINT_JOB"
            'Camera': input_data_dict['Camera'],
            'ErrorType': "Command NOT IMPLEMENTED YET",     # FIX THIS!
        }
        return output_data_dict

    elif api_cmd == "API_STATUS":
        # stuff to do here
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_IMMEDIATE",
            'API': api_cmd,  # == "API_STATUS"
            'Camera': input_data_dict['Camera'],
            'ErrorType': "Command NOT IMPLEMENTED YET",     # FIX THIS!
        }
        return output_data_dict

    elif api_cmd == "API_REAR_CONVEYOR":
        # stuff to do here
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_IMMEDIATE",
            'API': api_cmd,  # == "API_REAR_CONVEYOR"
            'Camera': input_data_dict['Camera'],
            'ErrorType': "Command NOT IMPLEMENTED YET",     # FIX THIS!
        }
        return output_data_dict

    elif api_cmd == "API_TAKE_PICTURE":   #this may take as long as a second to respond, maybe.
        # stuff to do here
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_IMMEDIATE",
            'API': api_cmd,  # == "API_REAR_CONVEYOR"
            'Camera': input_data_dict['Camera'],
            'ErrorType': "Command NOT IMPLEMENTED YET",     # FIX THIS!
        }
        return output_data_dict

    else:
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_PROBLEM",
            'API': api_cmd,
            'Camera': input_data_dict['Camera'],
            'ParsingError': False,
            'NetCmdError': False,
            'APIError': True,
            'SizeError': False,
            'Status': "Invalid API Command",
            'ErrorDetails': "Client sent invalid API Command"}
        return output_data_dict


# -----------------------------------------------------------------------------------------------------------
def net_request_action(input_data_dict):
    # This handles:  NET_REQUEST_ACTION
    # Commands allowed: API_EXAMINE_PLATEN_PAGE,  API_CHECK_PLATEN_PUNCH,  API_EXAMINE_OUTFEED_PAGE, API_REBOOT
    # returns dictionary: output_data_dict
    api_cmd = input_data_dict["API"]

    if api_cmd == "API_EXAMINE_PLATEN_PAGE":
        return examine_platen_page(input_data_dict)

    elif api_cmd == "API_CHECK_PLATEN_PUNCH":
        return check_platen_punch(input_data_dict)

    elif api_cmd == "API_EXAMINE_OUTFEED_PAGE":
        return examine_outfeed_page(input_data_dict)

    elif api_cmd == "API_REBOOT":
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_ACK",
            'API': api_cmd,  # == "API_REBOOT"
            'Camera': input_data_dict['Camera'],
            'Reboot': True      # special flag that tells caller to reboot RPi after server ACK response sent over network
        }
        return output_data_dict     # Send back ack before we actually do the reboot.

    else:   # unsupported API cmd
        output_data_dict = {
            'NetCmd': "NET_RESPONSE_PROBLEM",
            'API': api_cmd,
            'Camera': input_data_dict['Camera'],
            'ParsingError': False,
            'NetCmdError': False,
            'APIError': True,
            'SizeError': False,
            'ErrorType': "Invalid API Command",
            'ErrorDetails': "Client sent NET_REQUEST_ACTION message with invalid API Command: %s" % api_cmd}
        return output_data_dict


# -----------------------------------------------------------------------------------------------------------
def net_request_poll(data_dict):
    # This handles:  NET_REQUEST_POLL
    # Command allowed: command used in most recent NET_REQUEST_ACTION
    # returns dictionary: output_data_dict
    return 0   # TBD


# -----------------------------------------------------------------------------------------------------------
def net_request_abort(data_dict):
    # This handles:  NET_REQUEST_ABORT
    # Command allowed: command used in most recent NET_REQUEST_ACTION
    # returns dictionary: output_data_dict
    return 0   # TBD


# This allows the socket to be reused immediately.
# Reference: https://stackoverflow.com/questions/6380057/python-binding-socket-address-already-in-use/18858817#18858817
class MyTCPServer(socketserver.TCPServer):
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)

# -----------------------------------------------------------------------------------------------------------
def launch_tcp_server(host, port):
    print(">Launching TCPServer: %s / %d" % (host,port))
    with MyTCPServer((host, port), ThreadedTCPRequestHandler) as server:
        print("It is running")
        server.serve_forever()


# -----------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    host, port = "10.1.10.14", 65400  # TODO: CHANGE THIS TO LOOK UP IP ADDR FROM NETWORK
    launch_tcp_server(host, port)      # this will run forever

    print(">tcp_server stopping")

