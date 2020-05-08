import re
import uuid
import requests
import itertools
from interpolate import interpolate
from requests.exceptions import Timeout
import random

# TODO: Make this configurable
ENVOY_ADDRESS = "http://127.0.0.1:15001"


class RequestNode(object):
    def __init__(self):
        self.url = None
        self.headers = {}
        self.body = ""
        self.children = []
        self.parent = None
        self.response_status = None
        self.response_headers = {}
        self.response_body = ""
        self.configuration = {}

    def add_parent(self, parent):
        parent.children.append(self)
        self.parent = parent

    def update_request(self, **kwargs):
        if "url" in kwargs:
            self.url = kwargs["url"]
        if "headers" in kwargs:
            self.headers = kwargs["headers"]

        if "body" in kwargs:
            self.body = kwargs["body"]

    def update_response(self, **kwargs):
        if "headers" in kwargs:
            self.response_headers = kwargs["headers"]

        if "body" in kwargs:
            self.response_body = kwargs["body"]

        if "status" in kwargs:
            self.response_status = kwargs["status"]

    def update_configuration(self, configuration={}):
        self.configuration = configuration


class SagaCoordinator(object):
    """
    A class that handles initiating transactions, and failing all of them
    if one of them fails.
    """

    def __init__(self, configuration, start_request_headers={}, start_request_body=""):
        self.configuration = configuration
        self.identifier = str(uuid.uuid4())
        self.root = RequestNode()
        self.root.update_configuration(self.configuration.get("matchRequest", {}))
        self.root.update_request(headers=start_request_headers, body=start_request_body)

    def execute_saga(self):
        """
        Perform a serial unicast over the set of transactions. If any of them
        fail, halt sending out more transactions, and issue compensating transactions
        for all of the transactions sent out so far.

        Returns:
            - `success`: Bool -> Whether all of the transactions succeeded without 
                                 incident.

            - `transactions_so_far`: List[(Dict, Dict)] -> 
                                All of the transactions that completed 
                                of whose unsuccessful response triggered us to issue 
                                compensating transactions. A transaction in the latter
                                category will always be found at the end of this list.
                                Each element in this list is a tuple of (headers sent
                                out in that transaction, the transaction configuration).

            - `failed_compensating_transactions` - List[(Dict, Response)] -> 
                                All of the compensating transactions that did not work.
                                By default, we keep retrying a compensating transaction
                                indefinitely unless a max retry is set. Each element in
                                this list is a tuple of (compensating transaction config,
                                the last response that transaction received).
        """

        transactions = self.configuration["onMatchedRequest"]


        l = list(range(len(transactions)))
        random.shuffle(l)
        for i in l:
        # for transaction in transactions:
            transaction = transactions[i]
            node = self.send(transaction, kind="TRANSACTION", parent=self.root)

            if self.is_successful(node, transaction["isSuccessIfReceives"]):
                node.add_parent(self.root)
                continue
            else:
                return (
                    False,
                    self.root.children,
                    self.issue_compensating_transactions(self.root.children),
                )

        return True, self.root.children, []

    def issue_compensating_transactions(self, transactions_so_far):

        failed_compensations = []

        for node in transactions_so_far:
            for compensating_transaction in node.configuration["onFailure"]:

                response_node = self.send(
                    compensating_transaction, kind="COMPENSATION", parent=node
                )

                if self.is_successful(
                    response_node, compensating_transaction["isSuccessIfReceives"]
                ):
                    response_node.add_parent(node)
                    continue

                else:
                    failed_compensations.append(response_node)

        return failed_compensations

    def is_successful(self, node, expected_responses):
        """
        Check if the response that was received matches one of the 
        ones we were waiting for
        """

        if not node.response_status:
            return False

        for expected_response in expected_responses:

            _, headers, body = self.resolve_interpolations(
                expected_response, parent=node
            )

            if node.response_status != expected_response["status-code"]:
                continue

            if headers and any(
                node.response_headers.get(header) != value
                for header, value in headers.items()
            ):
                continue

            if body and node.response_body != body:
                continue

            return True

        return False

    def prepare_node(self, transaction, parent, kind):

        url, headers, body = self.resolve_interpolations(transaction, parent=parent)

        headers.update(
            {"X-Qbox-TransactionID": self.identifier, "X-Qbox-Message-Type": kind}
        )

        node = RequestNode()
        node.update_configuration(transaction)
        node.update_request(url=url, headers=headers, body=body)

        return node

    def send(self, transaction, kind="TRANSACTION", parent=None):
        """ 
        Handle the complete lifecycle of a single transaction.
        """

        node = self.prepare_node(transaction, parent, kind)

        # IF the number of retries is not specified:
        #  - Always keep retrying compensating transactions unless one succeeds.
        #  - Cap the number of retries for transactions to just one.
        # This ensures safety for other services.
        maxIterations = transaction.get(
            "maxRetriesOnTimeout", None if kind == "COMPENSATION" else 1
        )

        for _ in itertools.repeat(0, times=maxIterations):

            response = None
            try:
                response = requests.request(
                    method=transaction["method"],
                    url=node.url,
                    headers=node.headers,
                    data=node.body,
                    timeout=transaction["timeout"],
                    # proxies={"http": ENVOY_ADDRESS, "https": ENVOY_ADDRESS},
                )
            except Timeout:
                continue

            node.update_response(
                status=response.status_code,
                headers=response.headers,
                body=response.text,
            )
            return node

        return node

    def resolve_interpolations(self, transaction, parent=None):

        url = None
        if "url" in transaction:
            url = self.interpolate(transaction["url"], parent=parent)

        headers = transaction.get("headers", {})
        for header, value in headers.items():
            headers[header] = self.interpolate(value, parent=parent)

        body = self.interpolate(transaction.get("body", ""), parent=parent)

        return url, headers, body

    def interpolate(self, line, parent):
        return interpolate(line, parent=parent, root=self.root, transactions=[])
