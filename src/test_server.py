import io
import yaml
import requests
import unittest
import requests_mock
from server import RequestHandler
from unittest.mock import patch, mock_open
from requests_toolbelt.utils import dump
from scapy.layers.http import HTTP, HTTPResponse, HTTPRequest


class TestableHandler(RequestHandler):
    def setup(self):
        self.rfile = io.BytesIO(self.request)
        self.wfile = None

    def finish(self):
        pass

    def handle(self):
        pass

    def test(self, wfile):
        self.wfile = wfile
        self.handle_one_request()


class HTTPRequestHandlerTestCase(unittest.TestCase):
    def test_proxy_behaviour(self):

        with requests_mock.Mocker() as m:
            m.get(
                "http://foo.svc",
                status_code=200,
                headers={"Content-Type": "application/json"},
                text="success",
            )

            raw = dump.dump_response(
                requests.get("http://foo.svc"),
                request_prefix="",
                response_prefix="@@@",
            )
            split = raw.split(b"@@@")
            raw_request = split[0]
            expected_response = HTTPResponse(b"".join(split[1:]))

            raw_request
            handler = TestableHandler(raw_request, (0, 0), None)

            write_file = io.BytesIO()
            handler.test(write_file)
            write_file.seek(0)

            response = HTTPResponse(write_file.read())

            self.assertEqual(response.Status_Code, expected_response.Status_Code)
            self.assertEqual(response.Content_Type, expected_response.Content_Type)
            self.assertEqual(response.load, expected_response.load)

    def test_saga_behaviour(self):

        configuration = {
            "host": "productpage.svc",
            "matchRequest": {
                "method": "GET",
                "url": "http://localhost:3001/",
                "headers": {"Start-Faking": "True"},
            },
            "onMatchedRequest": [
                {
                    "method": "GET",
                    "url": "http://ratings.svc/add/${parent.headers.Product-Id}",
                    "isSuccessIfReceives": [
                        {
                            "status-code": 200,
                            "headers": {"Content-type": "application/json"},
                        }
                    ],
                    "onFailure": [
                        {
                            "method": "GET",
                            "url": "http://ratings.svc/delete/${root.headers.Product-Id}",
                            "timeout": 3,
                            "maxRetriesOnTimeout": 1,
                            "isSuccessIfReceives": [
                                {
                                    "status-code": 200,
                                    "headers": {"Content-type": "application/json"},
                                }
                            ],
                        }
                    ],
                    "timeout": 30,
                    "maxRetriesOnTimeout": 3,
                },
                {
                    "method": "GET",
                    "url": "http://details.svc/details/add/${root.headers.Product-Id}",
                    "isSuccessIfReceives": [
                        {
                            "status-code": 200,
                            "headers": {"Content-type": "application/json"},
                        }
                    ],
                    "onFailure": [
                        {
                            "method": "GET",
                            "url": "http://details.svc/details/remove/${root.headers.Product-Id}",
                            "timeout": 3,
                            "maxRetriesOnTimeout": 1,
                            "isSuccessIfReceives": [
                                {
                                    "status-code": 200,
                                    "headers": {"Content-type": "application/json"},
                                }
                            ],
                        }
                    ],
                    "timeout": 30,
                    "maxRetriesOnTimeout": 3,
                },
            ],
            "onAllSucceeded": {
                "status-code": 200,
                "body": "Ratings: ${transaction[0].response.body}\nDetails: ${transaction[1].response.body}\n",
            },
            "onAnyFailed": {
                "status-code": 500,
                "body": "Ratings: ${transaction[0].response.body}\nDetails: ${transaction[1].response.body}\n",
            },
        }
        with requests_mock.Mocker() as m:
            m.get(
                "http://ratings.svc/add/12",
                status_code=200,
                headers={"Content-type": "application/json"},
                text="success",
            )
            m.get(
                "http://details.svc/details/add/12",
                status_code=200,
                headers={"Content-type": "application/json"},
                text="success again",
            )

            raw_request = b"GET / HTTP/1.1\r\nHost: http://localhost:3001\r\nUser-Agent: python-requests/2.9.1\r\nAccept-Encoding: gzip, deflate\r\nAccept: */*\r\nConnection: keep-alive\r\nStart-Faking: True\r\nProduct-Id: 12\r\n\r\n"

            with patch(
                "builtins.open", mock_open(read_data=yaml.dump(configuration))
            ) as mock_file:

                with patch("os.path.exists") as os_mock:
                    os_mock.return_value = True
                    handler = TestableHandler(raw_request, (0, 0), None)

                    write_file = io.BytesIO()
                    handler.test(write_file)
                    write_file.seek(0)

                    response = HTTPResponse(write_file.read())
                    self.assertEqual(response.Status_Code, b"200")
                    self.assertEqual(
                        response.load, b"Ratings: success\nDetails: success again\n"
                    )
