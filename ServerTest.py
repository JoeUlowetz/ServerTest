# echo_server.py

import socketserver
import json
import inspect
import time


# This is the custom Request Handler Class; an instance of this class is created for each request
class MyTCPSocketHandler(socketserver.StreamRequestHandler):
    """
    The RequestHandler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
        # self.request is the TCP socket connected to the client
        #
        # Several instance attributes are available here:
        #   self.request    the request; this is a socket object
        #   self.client_address
        #   self.server     the server instance, in case need to access per-server info
        # self.data = self.request.recv(1024).strip()
        while True:
            self.data = self.rfile.readline().strip()
            if len(self.data) == 0:
                print("(no more data)")
                break
            print("\n{} wrote:".format(self.client_address[0]))
            print(self.data)
            # just send back the same data, but upper-cased
            # self.request.sendall(self.data.upper())
            self.wfile.write(self.data.upper())
            if self.data == b'EOM':     # end of message(s) flag
                print("EOM -------------")
                break




if __name__ == "__main__":
    HOST, PORT = "10.1.10.14", 65403

    # instantiate the server, and bind to localhost on port 65400
    server = socketserver.TCPServer((HOST, PORT), MyTCPSocketHandler)

    # activate the server
    # this will keep running until Ctrl-C
    print("Press Ctrl-C to cancel.")
    while True:
        server.handle_request()

    #server.serve_forever()