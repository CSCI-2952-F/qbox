# Debian
FROM python:3.8.1-buster

ADD src/ .

RUN apt-get update -y

RUN pip3 install -r requirements.txt

CMD python3 qbox.py
