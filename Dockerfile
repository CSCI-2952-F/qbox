# Debian
FROM python:3.8.1-buster

RUN apt-get update -y

ADD src/ .

RUN pip3 install -r requirements.txt

CMD python3 qbox.py
