import unittest
import ServerTest2 as ClientLogic
# TODO: move client logic to different package; doesn't belong in something called "Server"
# TODO: in fact, this test_Server2.py file should be called something else; it is USED to test Camera net protocol



class TestMethods(unittest.TestCase):

    ip = "10.1.10.14"
    port = 65400

    @classmethod
    def setUpClass(cls) -> None:
        # Note: I have to assume the server is already running on the RPi before the unittest starts up
        # This message helps w/ telling where tests start/end on server screen
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_NOP",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)

    @classmethod
    def tearDownClass(cls) -> None:
        # This message helps w/ telling where tests start/end on server screen
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_NOP",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)

    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    """
    # ---[Demo tests]---------------------------------------------------------
    def test_demo1(self):
        self.assertEqual('foo'.upper(), 'FOO')
        assert True

    def test_demo2(self):
        self.assertTrue('FOO'.isupper())
        assert True

    @unittest.skip("demonstrating skipping")
    def test_demo3(self):
        self.assertFalse('Foo'.isupper())
        assert False

    
    # This will result in test result OK, but also list stack trace for the failure
    @unittest.expectedFailure
    def test_demo4(self):
        self.assertEqual(1, 0, "broken")

    def test_demo5(self):
        self.assertTrue('FOO'.isupper())
        assert True
    """

    """
    Message groupings within one socket connection request/response session:
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
    """

    # ---[Test for sending non-dictionary]----------------------------------------------
    def test_msg_Invalid_dict(self):
        # Note: Server would catch this if Client code did not
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, "string instead of dict")
        print("(T): -->",resp)
        self.assertIsInstance(resp, dict)
        self.assertEqual(resp["NetCmd"], "NET_RESPONSE_PROBLEM")
        self.assertEqual(resp["Status"],"Request was not a dictionary")
        self.assertEqual(resp["Response"], False)

    # ---[Test for problems that prevent sending out request]----------------------------------------------
    def test_msg_SizeTooBig(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "garbage",
            "Camera": "Test",
            "BigField": "x" * 3000
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        self.assertEqual(resp["NetCmd"], "NET_RESPONSE_PROBLEM")
        self.assertEqual(resp["Status"], "Request too large to send")
        self.assertEqual(resp["Response"], False)

    """
    #These slow down running the test, so don't need to run them all the time
    def test_msg_bad_network_port(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_PING",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, 1111, req_dict)
        print("(((T): -->",resp)
        self.assertEqual(resp["NetCmd"], "NET_RESPONSE_PROBLEM")
        self.assertEqual(resp["Response"], False)
        self.assertEqual(resp["Status"],"Socket connection refused")

    def test_msg_bad_IP(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_PING",
            "Camera": "Test"
        }
        resp = ClientLogic.client("9.9.9.9", 1111, req_dict)
        print("(((T): -->",resp)
        self.assertEqual(resp["NetCmd"], "NET_RESPONSE_PROBLEM")
        self.assertEqual(resp["Response"], False)
        self.assertEqual(resp["Status"],"Socket connection timed out")
    """

    # ---[Test for problems with IMMEDIATE requests]----------------------------------------------
    def test_msg_IMMEDIATE_API_Invalid(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "garbage",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        self.assertEqual(resp["NetCmd"], "NET_RESPONSE_PROBLEM")
        self.assertEqual(resp["Status"],"Invalid API Command")
        self.assertEqual(resp["ErrorDetails"], 'Client sent invalid API Command')
        self.assertEqual(resp["Response"], True)

    def test_msg_IMMEDIATE_Missing_API(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        self.assertEqual(resp["NetCmd"], "NET_RESPONSE_PROBLEM")
        self.assertEqual(resp["Status"],"Missing Request field(s)")
        self.assertEqual(resp["Response"], True)

    # ---[Test normal operation of Immediate Requests]----------------------------------------------
    def test_msg_IMMEDIATE_PING(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_PING",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        self.assertIsInstance(resp, dict)
        self.assertEqual(resp["NetCmd"], "NET_RESPONSE_IMMEDIATE")
        self.assertEqual(resp["API"], "API_PING")
        self.assertEqual(resp["Camera"], "Test")
        self.assertEqual(resp["Status"], "OK")
        self.assertEqual(resp["Response"], True)

    def test_msg_IMMEDIATE_START_HARDWARE(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_START_HARDWARE",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        assert False

    """
    def test_msg_IMMEDIATE_START_PRINT_JOB(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_START_PRINT_JOB",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        assert False

    def test_msg_IMMEDIATE_STATUS(self):
        req_dict = {
            "NetCmd": "NET_REQUEST_IMMEDIATE",
            "API": "API_STATUS",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        assert False

    def test_msg_IMMEDIATE_REAR_CONVEYOR(self):
        req_dict = {
            "NetCmd": "API_REAR_CONVEYOR",
            "API": "API_STATUS",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        assert False

    def test_msg_IMMEDIATE_TAKE_PICTURE(self):
        req_dict = {
            "NetCmd": "API_TAKE_PICTURE",
            "API": "API_STATUS",
            "Camera": "Test"
        }
        resp = ClientLogic.client(TestMethods.ip, TestMethods.port, req_dict)
        print("(T): -->",resp)
        assert False
    """

if __name__ == '__main__':
    unittest.main()

