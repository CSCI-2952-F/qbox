local-development:
	docker build -t qbox .  && docker run -it -p 80:3001 qbox

run-local-tests:
	black .
	docker build -t qbox .  && docker run -it qbox python3 -m unittest discover