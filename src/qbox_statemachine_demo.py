class QboxConfig():
    SUCCESS_200 = 1
    SUCCESS_PAYLOAD = 2
    FAIL_404 = 3
    FAIL_REST = 4
    SENDBACK_200 = 5
    SENDBACK_PAYLOAD = 6
    SENDBACK_404 = 7
    DoNothing = 8

config = {
    "appname": "frontend",
    "onrequest": {
        "requestname": "sendreq",
        "transactions": [
            {
                "dstname": "nodejs",
                "request": "post_nodejs",
                "success": QboxConfig.SUCCESS_200,
                "fail": QboxConfig.FAIL_REST,
                "compensation": "depost_nodejs",
                
                "timeout": 30
            },
            {
                "dstname": "ruby",
                "request": "post_ruby",
                "success": QboxConfig.SUCCESS_200,
                "fail": QboxConfig.FAIL_REST,
                "compensation": "depost_ruby",
                "timeout": 30
            },
            {
                "dstname": "ruby2",
                "request": "post_ruby2",
                "success": QboxConfig.SUCCESS_200,
                "fail": QboxConfig.FAIL_REST,
                "compensation": "depost_ruby2",
                "timeout": 30
            },
        ],
        "onSuccess": QboxConfig.SENDBACK_200,
        "onFail": QboxConfig.SENDBACK_404,
    }
}

def send_requests(config):
    print("requests sent")
    return 1

test1 = [("nodejs", QboxConfig.FAIL_404), ("ruby", QboxConfig.SUCCESS_200), ("ruby2", QboxConfig.FAIL_404)]
test_index = 0
def get_respond():
    global test_index
    res = test1[test_index]
    test_index += 1
    return res

def send_compensation(config):
    print("compensation sent")
    return 1

def send_back_result_to_requestor(config, status):
    if status:
        s = "failed"
    else:
        s = "succeed"
    print("result is sent back to requestor, this time it is " + s)
    return 1

class StateInfo:
    INIT = 1
    AWAIT = 2
    SUCCESS = 3
    FAIL = 4
    COMPENSATED = 5
    PARTIALLY_FAIL = 6
    ALL_FAIL = 7
    ALL_SUCCESS = 8
    def __init__(self, config, bitmap):
        self.config = config
        self.bitmap = bitmap
    
    def change_state(self, i, state):
        self.bitmap[i] = state

    def get_state(self, i):
        return self.bitmap[i]

    def get_all_response(self):
        for bit in self.bitmap:
            if bit == StateInfo.INIT or bit == StateInfo.AWAIT:
                return False
        return True

    def get_response_status(self):
        has_fail = False
        has_success = False
        for bit in self.bitmap:
            if bit == StateInfo.FAIL:
                if has_success:
                    return StateInfo.PARTIALLY_FAIL
                else:
                    has_fail = True
            elif bit == StateInfo.SUCCESS:
                if has_fail:
                    return StateInfo.PARTIALLY_FAIL
                else:
                    has_success = True
            else:
                assert(0)
        if has_fail:
            return StateInfo.ALL_FAIL
        else:
            return StateInfo.ALL_SUCCESS

    def __repr__(self):
        s = ''
        for bit, transaction in zip(self.bitmap, config["onrequest"]["transactions"]):
            s += "transaction: " + transaction["dstname"] + " state is: "
            if bit == StateInfo.INIT:
                s += "initial"
            elif bit == StateInfo.AWAIT:
                s += "awaiting response"
            elif bit == StateInfo.SUCCESS:
                s += "success"
            elif bit == StateInfo.FAIL:
                s += "fail"
            elif bit == StateInfo.COMPENSATED:
                s += "compensated"
            s += "\n"
        return s
class State:
    start_state = 1
    awaiting_state = 2
    compensation_state = 3
    finish_state = 4

class StateMachine:
    def __init__(self, config):
        self.config = config
        self.transaction_number = len(config["onrequest"]["transactions"])
        self.state_info = StateInfo(config, [StateInfo.INIT for i in range(self.transaction_number)])
        self.state_type = State.start_state
        self.response = [None] * self.transaction_number
        self.saga_fail = False

    def transition(self):
        if self.state_type == State.start_state:
            res = send_requests(config)    
            if res:
                for i in range(self.transaction_number):
                    self.state_info.change_state(i, StateInfo.AWAIT)
                self.state_type = State.awaiting_state
        elif self.state_type == State.awaiting_state:
            srcname, info = get_respond()
            for i, transaction in enumerate(self.config["onrequest"]["transactions"]):
                if transaction["dstname"] == srcname:
                    if info == transaction["success"]:
                        if self.state_info.get_state(i) == StateInfo.AWAIT:
                            self.state_info.change_state(i, StateInfo.SUCCESS)
                        else:
                            print("somethin weird")
                    elif info == transaction["fail"] or transaction["fail"] == QboxConfig.FAIL_REST:
                        if self.state_info.get_state(i) == StateInfo.AWAIT:
                            self.state_info.change_state(i, StateInfo.FAIL)
                        else:
                            print("somethin weird")
            if self.state_info.get_all_response():
                res = self.state_info.get_response_status()
                if res in [StateInfo.ALL_SUCCESS, StateInfo.ALL_FAIL]:
                    self.state_type = State.finish_state
                    if res == StateInfo.ALL_FAIL:
                        self.saga_fail = True
                else:
                    self.state_type = State.compensation_state
        
        elif self.state_type == State.compensation_state:
            self.saga_fail = True
            all_compensated = True
            for i, transaction in enumerate(self.config["onrequest"]["transactions"]):
                if self.state_info.get_state(i) == StateInfo.FAIL:
                    res = send_compensation(self.config)
                    if res:
                        self.state_info.change_state(i, StateInfo.COMPENSATED)
                    else:
                        all_compensated = False
            if all_compensated:
                self.state_type = State.finish_state
        elif self.state_type == State.finish_state:
            res = send_back_result_to_requestor(self.config, self.saga_fail)
            if res:
                return True
        return False

        
if __name__ == "__main__":
    
    sm = StateMachine(config)
    print(sm.state_info)
    while not sm.transition():
        print(sm.state_info)

















