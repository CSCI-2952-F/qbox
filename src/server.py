import logging
import requests
from functools import partial
from interpolate import interpolate
from configuration import ConfigurationStore
from coordinator import SagaCoordinator, RequestNode, ENVOY_ADDRESS
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

logging.basicConfig(level=logging.DEBUG)

ADDRESS = "0.0.0.0"
PORT = 3001


class RequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.body = None
        self.configurations = ConfigurationStore().get_config()
        logging.info(f"Configurations == {self.configurations}")
        super(RequestHandler, self).__init__(*args, **kwargs)

    def do_GET(self):
        return self.handle_connection()

    def do_POST(self):
        return self.handle_connection()

    def do_PUT(self):
        return self.handle_connection()

    def do_PATCH(self):
        return self.handle_connection()

    def do_DELETE(self):
        return self.handle_connection()

    def do_OPTIONS(self):
        return self.handle_connection()

    def do_HEAD(self):
        return self.handle_connection()

    def do_TRACE(self):
        return self.handle_connection()

    def do_CONNECT(self):
        return self.handle_connection()

    def get_body(self):
        content_len = int(self.headers.get("content-length", 0))
        if self.body:
            return self.body
        body = self.rfile.read(content_len)
        self.body = body
        return self.body

    def handle_connection(self):
        logging.info(f"Handling request {self.headers} {self.get_body()}")
        if self.configurations:
            is_request, configuration_index = self.is_saga_request()
            if is_request:
                logging.info("Identified a transaction request!")
                status, headers, body = self.execute(configuration_index)
                self.send_response(status)
                for header, value in headers.items():
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
                return

        logging.info("Decided it was not a transaction")
        url = self.headers["Host"]
        try:
            logging.info(f"Sending request to {url}")
            response = requests.request(
                method=self.command,
                # NOTE: We're assuming HTTPS traffic is never sent to us!
                # This is fine for our proof-of-concept - Envoy in practice
                # automatically upgrades all HTTP traffic to HTTPS if configured
                # to do so with the appropriate TLS certificates.
                url=url if url.startswith("http://") else f"http://{url}",
                headers=self.headers,
                data=self.get_body(),
                # proxies={"http": ENVOY_ADDRESS, "https": ENVOY_ADDRESS},
            )
            logging.info(f"Got response back of {response.status_code}")
            self.send_response(response.status_code)
            for header, value in response.headers.items():
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(response.content)
        except Exception as e:
            self.send_error(599, "Error proxying: {}".format(e))

    def is_saga_request(self):

        logging.info("Checking if Saga request...")
        for index, configuration in enumerate(self.configurations):
            config = configuration["matchRequest"]
            headers = config.get("headers", {})
            body = config.get("body", "")

            constructed_url = f"{self.headers['Host']}{self.path}"
            if not constructed_url.startswith("http://"):
                constructed_url = f"http://{constructed_url}"

            if config["url"] != constructed_url:
                continue
            if config["method"] != self.command:
                continue
            if headers and any(
                self.headers.get(header) != value for header, value in headers.items()
            ):
                continue
            if body and self.get_body() != body:
                continue

            return (True, index)
        return (False, None)

    def execute(self, index):
        """
        Handle all requests as deemed necessary.
        """

        coordinator = SagaCoordinator(
            self.configurations[index],
            start_request_headers=self.headers,
            start_request_body=self.get_body(),
        )
        success, transactions, failed_compensations = coordinator.execute_saga()
        context = {
            "parent": RequestNode(),
            "root": coordinator.root,
            "transactions": transactions,
        }

        if success:
            return self.respond(self.configurations[index]["onAllSucceeded"], context)
        else:
            return self.respond(self.configurations[index]["onAnyFailed"], context)

    def respond(self, config, context):

        headers = {}
        for header, value in config.get("headers", {}):
            headers[header] = interpolate(value, **context)
        body = interpolate(config.get("body", ""), **context)
        return config["status-code"], headers, body


if __name__ == "__main__":

    logging.info("Started our request")

    config = ConfigurationStore().get_config()

    httpd = ThreadingHTTPServer((ADDRESS, PORT), RequestHandler)
    httpd.serve_forever()
