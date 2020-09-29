FROM python:latest

COPY mnoc-sync /opt/
COPY mnoc-jobtools /opt/
COPY requirements.txt /opt/

WORKDIR /opt/

RUN python -m pip install -r requirements.txt

CMD [ "export", "PYTHONPATH=${PYTHONPATH}:/opt/" ]
CMD [ "python3", "/opt/mnoc_sync/sync.py" ]
