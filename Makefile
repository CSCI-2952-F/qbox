local-development:
	docker build -t qbox .  && docker run -it -p 80:80 qbox