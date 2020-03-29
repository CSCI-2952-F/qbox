lint:
	black .

local-inspect: lint
	docker build -t qbox:latest .  && docker run -it -p 3001:3001 qbox /bin/bash

local-development: lint
	docker build -t qbox:latest .  && docker run -it -p 3001:3001 qbox

run-local-tests: lint
	docker build -t qbox:latest .  && docker run -it qbox python3 -m unittest discover

push-to-dockerhub: lint run-local-tests
	docker tag qbox akshatm/qbox:latest
	docker push akshatm/qbox:latest