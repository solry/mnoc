# Base mnoc image with installed dependencies

FROM python:latest

COPY requirements.txt /opt/

WORKDIR /opt/

RUN python -m pip install -r requirements.txt