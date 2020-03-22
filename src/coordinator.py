import uuid
import requests
import itertools
from requests.exceptions import Timeout

# TODO: Make this configurable
ENVOY_ADDRESS = "127.0.0.1:15001"


class SagaCoordinator(object):
    """
    A class that handles initiating transactions, and failing all of them
    if one of them fails.
    """

    def __init__(self, configuration):
        self.configuration = configuration
        self.identifier = uuid.uuid4()

    def execute_saga(self, parent_headers={}):
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
        transactions_so_far = []

        for transaction in transactions:
            headers, response = self.send(
                transaction, kind="TRANSACTION", parent_headers=parent_headers
            )
            transactions_so_far.append((headers, transaction))

            if self.is_successful(response, transaction["isSuccessIfReceives"]):
                continue
            else:
                return (
                    False,
                    transactions_so_far,
                    self.issue_compensating_transactions(transactions_so_far),
                )

        return True, transactions_so_far, []

    def issue_compensating_transactions(self, transactions_so_far):

        failed_compensations = []

        for headers, transaction in transactions_so_far:
            for compensating_transaction in transaction["onFailure"]:
                _, response = self.send(
                    compensating_transaction,
                    kind="COMPENSATION",
                    parent_headers=headers,
                )

                if self.is_successful(
                    response, compensating_transaction["isSuccessIfReceives"]
                ):
                    continue

                else:
                    failed_compensations.append((compensating_transaction, response))

        return failed_compensations

    def is_successful(self, response, expected_responses):
        """
        Check if the response that was received matches one of the 
        ones we were waiting for
        """

        if not response:
            return False

        for expected_response in expected_responses:

            if response.status_code != expected_response["status-code"]:
                continue

            if expected_response.get("headers", {}) and any(
                response.headers.get(header) != value
                for header, value in expected_response["headers"].items()
            ):
                continue

            if (
                expected_response.get("body", None)
                and response.text != expected_response["body"]
            ):
                continue

            return True

        return False

    def send(self, transaction, kind="TRANSACTION", parent_headers=None):
        """ 
        Handle the complete lifecycle of a single transaction.
        """

        headers = parent_headers or {}
        headers.update(
            {"X-Qbox-TransactionID": self.identifier, "X-Qbox-Message-Type": kind}
        )
        headers.update(transaction.get("headers", {}))

        body = transaction.get("body", None)

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
                    url=transaction["url"],
                    headers=transaction,
                    data=transaction,
                    timeout=transaction["timeout"],
                    proxies={"http": ENVOY_ADDRESS, "https": ENVOY_ADDRESS},
                )
            except Timeout:
                continue

            return headers, response

        return headers, None
