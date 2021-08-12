# ServerTest2.py
# This version allows multiple different clients to talk to server async at the same time

# async.py

import socket
import threading
import socketserver
import time
import json
import traceback
import os

# for RPI especially:
from examine_platen_page import examine_platen_page
from examine_outfeed_page import examine_outfeed_page
from check_platen_punch import check_platen_punch


# This is base version sending simple strings; next step is convert dict to string

BUFFER_SIZE = 2048      # For the moment, assume all messages will fit in one buffer length
DELTA = 100             # allow for overhead in socket buffer when comparing if message is too large
ENCODING = 'ascii'      # use 'ascii' or 'utf-8'
SERVER_ERROR_RETURN = b"ERROR SERVER RECEIVED MESSAGE THAT WAS NOT A DICTIONARY"   # This flags an error to caller

keep_running = True
server = None
server_thread = None

"""
This is "version 2" network design.

* The "client" is the SWZP printer software on the PC
* The "server" is the Raspberry Pi with a camera attached.

* all action driven from client; if the server needs to send something to the client, the client must poll for it
* every message from the client will result in a response from the server.
* the socket connection is opened fresh each time the client wants to send a message to the server; it is kept open
  until the server sends a response message, and then the socket is closed.
* the client is effectively blocked until the server sends a response, or a timeout occurs
* if the server will take a long time to respond to a client request, the server should immediately ACK the
  request in order to close the socket connection, and then independently work on the request. The client can
  send polling query requests to the server to see if it is done yet; the server will respond with either "not
  done yet", or "done, here are the results".  The client polling request will have the option to tell the server
  to abort the current activity if desired.
* "ACTION" requests can only be handled one at a time on one server. The previous action must be completed (or aborted) 
  before the next action request can be sent. This does not apply to "IMMEDIATE" messages; those can be sent and 
  replied to while waiting for some action to complete.
* we are going to limit the size of messages across the network to 2048; multi-part messages not supported. The size
  limit is applied to the JSON-encoded dictionary object when sent from either client or server. This will preclude
  sending image files across the network this way (they can be handled at the file level with Samba).


Messages/Requests that originate from the Client(PC):
-------------------------------------------
    NET_REQUEST_IMMEDIATE ex. ping
    NET_REQUEST_ACTION    ex. taking a photo and analyzing it. Something that cannot be completed immediately by the server
    NET_REQUEST_POLL      sent after sending a "ACTION_POLLED" request, to see if it is finished
    NET_REQUEST_ABORT     sent after sending a "ACTION_POLLED" request that is taking too long to complete

Messages/Responses returned from the Server(Raspberry Pi):
---------------------------------------------------------
    NET_RESPONSE_IMMEDIATE   Server immediately completes action request and sends response; no polling needed
    NET_RESPONSE_ACK  acknowledge an action request that will take a long time; client will have to poll
        in order to later get the actual response result. The "ACK" message just means that the server received
        the request and will begin working on it now.
    NET_RESPONSE_NAK   Server sends this in response to a client "ACTION" request when it is already working
        on a previous request that has not been completed yet. Action requests cannot be queued because the
        client will usually expect these action requests to be started immediately upon receipt, such as taking an
        image and analyzing it.
    NET_RESPONSE_WAIT     Server sends this in response to a client "POLL" message when it has not completed
        the requested action yet; the server will continue working on the request until finished, or the client tells
        it to "ABORT" the action.
    NET_RESPONSE_RESULTS  Server sends this in response to a client "POLL" message that has completed, and the
        response includes the results from the request. Once this "RESPONSE_RESULTS" is sent, the client should not
        poll again.
    NET_RESPONSE_PROBLEM  The server had a problem with the request from the client; for example, the client requested
        a something involving the camera before the camera was initialized


Message groupings within one socket connection request/response session:
-----------------------------------------------------------------------
Client:     NET_REQUEST_IMMEDIATE
Server:     NET_RESPONSE_IMMEDIATE -or-
            NET_RESPONSE_PROBLEM (unable to process request for some reason)

Client:     NET_REQUEST_ACTION
Server:     NET_RESPONSE_ACK (action will begin now on server) -or-
            NET_RESPONSE_NAK (previous action not completed yet) -or-
            NET_RESPONSE_PROBLEM (unable to process request for some reason)

Client:     NET_REQUEST_POLL
Server:     NET_RESPONSE_WAIT (not finished yet) -or-
            NET_RESPONSE_RESULTS (finished, here are the results) -or-
            NET_RESPONSE_NAK (no work is currently being done) -or-
            NET_RESPONSE_PROBLEM (unable to process request for some reason)

Client:     NET_REQUEST_ABORT
Server:     NET_RESPONSE_ACK (action cancelled) -or-
            NET_RESPONSE_RESULTS (just finished before abort sent; client can use results or ignore) -or-
            NET_RESPONSE_NAK (unable because no longer working on request) -or-
            NET_RESPONSE_PROBLEM (unable to process request for some reason)
            
######################
Client REQUEST fields:
######################

* NetCmd = "NET_REQUEST_IMMEDIATE"
  API = "API_PING"      # test that we can talk to the server, and that it sends a response back
  Camera = "Platen" or "Outfeed" or "Stacker"

* NetCmd = "NET_REQUEST_IMMEDIATE"
  API = "API_START_HARDWARE"    # This starts the camera, so must be called before any imaging actions
  Camera = "Platen" or "Outfeed" or "Stacker"
  x_resolution = number
  y_resolution = number
  image_format = JPG for now
  page_size = string: "12x8" or "12x12" or...   #  this is needed by OpenCV logic for Platen punch check

* NetCmd = "NET_REQUEST_IMMEDIATE"
  API = "API_START_PRINT_JOB"       # send this whenever a print job starts/resumes
  Camera = "Platen" or "Outfeed" or "Stacker"
  build_id = build ID / traveler number
  archive_rpi_images = True/False       Applies to all Action examine/check until changed

* NetCmd = "NET_REQUEST_IMMEDIATE"
  API = "API_STATUS"
  Camera = "Platen" or "Outfeed" or "Stacker"
  status_detail = bit flag (5 bits) to control desired info (see common.py, build_rpi_info() for details)
  
* NetCmd = "NET_REQUEST_IMMEDIATE"
  API = "API_REAR_CONVEYOR"     # only applies to outfeed camera
  Camera = "Outfeed"
  action = 0:stop, 1:start [verify this]

* NetCmd = "NET_REQUEST_IMMEDIATE"
  API = "API_TAKE_PICTURE"          # take picture immediately, not used for analysis, just to test the camera
  Camera = "Platen" or "Outfeed" or "Stacker"
  archive_rpi_images = True/False  [?if it doesn't archive the image, it won't be available anywhere?!]
  x_resolution = number
  y_resolution = number
  image_format = JPG for now

--------------------------------

  NetCmd = "NET_REQUEST_ACTION"
  API = "API_EXAMINE_PLATEN_PAGE"
  Camera = "Platen"
  page_num = page number, -1 for final header page
  config_pt_1 = number pair     # used by OpenCV logic
  config_pt_2 = number pair
  image_only = True means disable OpenCV logic and only take the examine platen image, for testing
  status_detail = bit flag (5 bits) to control desired info (see common.py, build_rpi_info() for details), same feature as API_STATUS

  NetCmd = "NET_REQUEST_ACTION"
  API = "API_CHECK_PLATEN_PUNCH"
  Camera = "Platen"
  page_num = page number, -1 for final header page
  image_only = True means disable OpenCV logic and only take the examine platen image, for testing
  status_detail = bit flag (5 bits) to control desired info (see common.py, build_rpi_info() for details), same feature as API_STATUS

  NetCmd = "NET_REQUEST_ACTION"
  API = "API_EXAMINE_OUTFEED_PAGE"
  Camera = "Outfeed"
  page_num = page number, -1 for final header page
  image_only = True means disable OpenCV logic and only take the examine platen image, for testing
  status_detail = bit flag (5 bits) to control desired info (see common.py, build_rpi_info() for details), same feature as API_STATUS

  NetCmd = "NET_REQUEST_ACTION"
  API = "API_REBOOT"
  Camera = "Platen" or "Outfeed" or "Stacker"

---------------------------

  NetCmd = "NET_REQUEST_POLL"
  API = most recent command used in NET_REQUEST_ACTION  (must match or problem)
  Camera = "Platen" or "Outfeed" or "Stacker"

---------------------------

  NetCmd = "NET_REQUEST_ABORT"
  API = most recent command used in NET_REQUEST_ACTION  (must match or problem)
  Camera = "Platen" or "Outfeed" or "Stacker"


######################
Server RESPONSE fields:
######################
  NetCmd = "NET_RESPONSE_PROBLEM"
  API = incoming API if available, else 'N/A'
  Camera = incoming Camera if available, else 'N/A'
  ParsingError        True if server unable to parse client request, including client sending something that is not a dictionary
  NetCmdError         True if client sent unsupported NetCmd
  APIError            True if client sent unsupported API Command
  SizeError           True if SERVER tried to send response back to client that was too large for network buffer
  Status              "Failed/Problem"
  ErrorType           text
  ErrorDetails        text details

  NetCmd = "NET_RESPONSE_IMMEDIATE"
  API = incoming API    (Commands allowed: API_PING, API_START_HARDWARE?, API_STATUS, API_REAR_CONVEYOR?, API_TAKE_PICTURE)
  Camera = incoming Camera
  Status = "Success" or may be other text depending on API command
  if API == API_STATUS, then the response can include some combination of the following fields:
    disk_usage, uptime, watchdog_count, watch_recent, cpu_temp, top, debian, release, kernal, processes
  if API == API_TAKE_PICTURE, then response includes field:
    image_filename  This is name of image just captured on the RPi, including full path to it.

  NetCmd = "NET_RESPONSE_ACK"
  API = incoming API    (Commands allowed:   API_EXAMINE_PLATEN_PAGE,  API_CHECK_PLATEN_PUNCH,  API_EXAMINE_OUTFEED_PAGE, API_REBOOT)
  Camera = incoming Camera
  Status = "Success; Camera %d started action %s" % (Camera,API)
  Reboot              True to reboot RPi after current command finished, only for API == "API_REBOOT" (test this) [client does not need this field but will receive it anyway]

  NetCmd = "NET_RESPONSE_NAK"
  API = incoming API    (Commands allowed:   API_EXAMINE_PLATEN_PAGE,  API_CHECK_PLATEN_PUNCH,  API_EXAMINE_OUTFEED_PAGE)
  Camera = incoming Camera
  Status = "Failure/NET_REQUEST_ACTION/<incoming_API>; Camera %s still busy with previous action %s" % (API, Camera, current_API) -or-
           "Failure/NET_REQUEST_POLL/<incoming_API>; Camera %s is not currently working on any action" % (API, Camera)   -or-
           "Failure/NET_REQUEST_ABORT/<incoming_API>; Camera %s is not currently working on any action" % (API, Camera)

  NetCmd = "NET_RESPONSE_WAIT"
  API = incoming API    (Commands allowed:   API_EXAMINE_PLATEN_PAGE,  API_CHECK_PLATEN_PUNCH,  API_EXAMINE_OUTFEED_PAGE)
  Camera = incoming Camera
  duration = how many seconds since action started
  Status = "Waiting"

  NetCmd = "NET_RESPONSE_RESULTS"
  API = incoming API    (Commands allowed:   API_EXAMINE_PLATEN_PAGE,  API_CHECK_PLATEN_PUNCH,  API_EXAMINE_OUTFEED_PAGE)
  Camera = incoming Camera
  duration = how many seconds since action started
  completed_duration = how many seconds from action request until it actually completed
  Status = "Completion"

#
"""


# -----------------------------------------------------------------------------------------------------------
class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
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
        # print("{S}: Server working with:", data_str)

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


# -----------------------------------------------------------------------------------------------------------
# This is code for testing the server logic; this is sample CLIENT code; it uses the network even though both parts are running on the same computer/program
def client(ip, port, message_dict):
    # client_error = {"Status": "Nothing sent out; problem sending message"}
    # print("[C]: Client sending:", message_dict)
    if type(message_dict) is not dict:
        # print("[C]: Client tried to send a message that is not a dictionary; nothing done")
        return {
            "NetCmd": "NET_RESPONSE_PROBLEM",
            "Status": "Request was not a dictionary",
            "Response": False
        }

    message_dict['TS1'] = round(time.time(), 3)       # when request sent out by client (PC clock)

    # turn dictionary into json string
    message_string = json.dumps(message_dict)
    if len(message_string) >= (BUFFER_SIZE-DELTA):
        # print("[C]: message is too large to fit in socket buffer; nothing was done.")
        return {
            "NetCmd": "NET_RESPONSE_PROBLEM",
            "Status": "Request too large to send",
            "Response": False
        }

    t1 = time.time()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # Note: this timeout setting will affect both how long the client
        # waits to initially connect to the Server, and also how long it
        # waits for the Server to return a Response to its request.
        # We may want to set this even smaller, since the client will block waiting.
        sock.settimeout(3)
        try:
            sock.connect((ip, port))
        except ConnectionRefusedError:
            print("[C]: Connection refused!")
            # TODO: future: automatic retry?
            return {
                "NetCmd": "NET_RESPONSE_PROBLEM",
                "Response": False,
                "ErrorDetails": "Socket connection refused: %s / %s" % (ip, port),
                "Status": "Socket connection refused"
            }
        except socket.timeout:
            print("[C]: Socket timed out!")
            # TODO: future: automatic retry?
            return {
                "NetCmd": "NET_RESPONSE_PROBLEM",
                "Response": False,
                "ErrorDetails": "Socket connection timed out: %s / %s" % (ip, port),
                "Status": "Socket connection timed out"
            }

        # convert string to bytes so it can be sent to socket
        out_bytes = bytes(message_string, ENCODING)      # maybe use utf-8

        # #################################
        # send client request out socket
        # #################################
        sock.sendall(out_bytes)

        # #################################
        # Wait for server's response (this is blocking)
        # #################################
        try:
            resp_bytes = sock.recv(BUFFER_SIZE)
        except socket.timeout:
            print("[C]: THREW a timeout EXCEPTION waiting for a server response!!!")
            t2 = time.time()
            print("[C]: Time Difference:",round(t2-t1,2))
            # #################################
            # This is where the CLIENT would deal with a timeout when the server didn't respond quickly enough
            # #################################
            return {
                "NetCmd": "NET_RESPONSE_PROBLEM",
                "Response": False,
                "Status": "Timeout occurred waiting for Response from server"
            }


        # turn bytes into string
        resp_str = str(resp_bytes, ENCODING)
        # print("[C]: Client working with input:", resp_str)

        try:
            resp_dict = json.loads(resp_str)
        except SyntaxError:
            # Server returned something that was not valid json; this should not happen
            print("[C]: Error: client received something that is not a valid message (not valid json)")
            print("[C]: Client received from server:", resp_str)
            return {"Status": "Error: Server response was not a valid message (not valid json)"}

        if type(resp_dict) is not dict:
            print("[C]: **Client received a message from the server that did not evaluate to a dictionary")  # should not happen
            print("[C]: ", type(resp_dict))
            print("[C]: ", resp_dict)
            return {
                "Status": "Error: Server response did not evaluate to a dictionary"}

        if 'NetCmd' not in resp_dict:   # this shouldn't happen either
            print("[C]: **Client received a dictionary response from the server that did not include a 'NetCmd' field; cannot parse")
            print(resp_dict)
            return {"Status": "Error: Server response did not contain 'NetCmd' field so unable to understand it"}

        resp_dict['TS4'] = round(time.time(),3)      # when response received by client (PC clock)
        resp_dict['Delta1'] = round(round(time.time(),3) - message_dict['TS1'],3)     # time from client sent request to receive response
        resp_dict['Delta2'] = round(resp_dict['TS3'] - resp_dict['TS2'],3)   # time server spend processing the request

        # #################################
        # At this point, we have a valid dictionary that was returned
        # to us by the server and we should be able to understand it;
        # see if the server accepted the request
        # #################################
        """    
        if resp_dict['NetCmd'] == "NET_RESPONSE_PROBLEM":
            # print("[C]: **Client received response from server that the server had a problem with our request and could not process it")
            if resp_dict['ParsingError']:
                print("[C]: -> Server reported Parsing Error")
            if resp_dict['NetCmdError']:
                print("[C]: -> Server reported that our request did not have valid NetCmd")
            if resp_dict['APIError']:
                print("[C]: -> Server reported that our request did not have a valid API command")
            if resp_dict['SizeError']:
                print("[C]: -> Server reported that the response it wanted to send was too large to fit in network buffer")
            # print("[C]: Status:",resp_dict['Status'])
            # print("[C]: ErrorDetails:",resp_dict['ErrorDetails'])
        elif resp_dict['NetCmd'] == "NET_RESPONSE_IMMEDIATE":
            print("[C]: **Client received NET_RESPONSE_IMMEDIATE")
            print("[C]: ", resp_dict)
        elif resp_dict['NetCmd'] == "NET_RESPONSE_ACK":
            print("[C]: **Client received NET_RESPONSE_ACK")
            print("[C]: ", resp_dict)
        elif resp_dict['NetCmd'] == "NET_RESPONSE_NAK":
            print("[C]: **Client received NET_RESPONSE_NAK")
            print("[C]: ", resp_dict)
        elif resp_dict['NetCmd'] == "NET_RESPONSE_WAIT":
            print("[C]: **Client received NET_RESPONSE_WAIT")
            print("[C]: ", resp_dict)
        elif resp_dict['NetCmd'] == "NET_RESPONSE_RESULTS":
            print("[C]: **Client received NET_RESPONSE_RESULTS")
            print("[C]: ", resp_dict)
        else:
            print("[C]: **Client received unsupported NetCmd (should not be able to happen)")
            print("[C]: ", resp_dict)
        """

        return resp_dict


def server_loop(server):    # NOT SURE IF THIS IS NEEDED OR NOT
    while keep_running:
        server.handle_request()


def launch_server():
    # port 0 means to select an arbitrary unused port
    HOST, PORT = "localhost", 54301

    global server
    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
    ip, port = server.server_address
    # ip = "8.8.8.8"  # FORCE ERROR

    # start a thread with the server.
    print("*** Server location:", ip, port)
    # the thread will then start one more thread for each request.
    global server_thread
    server_thread = threading.Thread(target=server.serve_forever)  # PROBLEM???: will this SUPPORT TIMEOUT FEATURE!!!!
    # server_thread = threading.Thread(target=server_loop,args=(server,))

    # exit the server thread when the main thread terminates
    server_thread.daemon = True
    server_thread.start()
    print("*** Server loop running in thread:", server_thread.name)
    return ip, port


def shutdown_server():
    print("*** Shutting down server thread")
    server.shutdown()
    global keep_running
    keep_running = False
    server_thread.join()
    print("*** Shutdown complete")


# -----------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    ip, port = launch_server()

    #print("Here@!")
    #time.sleep(3)
    #print("Leaving...")
    # #####################################
    # Put test cases in test_ServerTest3.py
    # #####################################
    #import test_ServerTest2
    #test_ServerTest2.test_handle()

    print("-[Test]------------------------------------------------------------------------------  ")
    req_dict = {
        "NetCmd": "NET_REQUEST_IMMEDIATE",
        "API": "API_START_HARDWARE",
        "Camera": "Test"
    }
    client(ip, port, req_dict)
    """

    print("-[Test]------------------------------------------------------------------------------  ")
    req_dict = {
        "NetCmd": "NET_REQUEST_IMMEDIATE",
        "API": "API_START_PRINT_JOB",
        "Camera": "Test"
    }
    client(ip, port, req_dict)

    print("-[Test #2]------------------------------------------------------------------------------  ")
    req_dict = {"NetCmd": "NET_REQUEST_IMMEDIATE", "API": "API_PING","Camera": "Test"}
    #my_dict['big'] = "x" * 1000
    client(ip, port, req_dict)

    print("-[Test #3]------------------------------------------------------------------------------  ")
    client(ip, port, "Hello World 3")

    print("-------------------------------------------------------------------------------  ")
    print(">>> server.shutdown now <<<")
    server.shutdown()
    keep_running = False
    # server_thread.join()
    # print("After join")
    # print("Waiting for additional clients...")
    # while True:
    #    time.sleep(1)
"""
    shutdown_server()

