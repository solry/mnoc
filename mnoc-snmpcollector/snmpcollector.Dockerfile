FROM python:latest

COPY mnoc-snmpcollector /opt/
COPY mnoc-jobtools /opt/
COPY requirements.txt /opt/

WORKDIR /opt/

RUN python -m pip install -r requirements.txt

CMD [ "export", "PYTHONPATH=${PYTHONPATH}:/opt/" ]
CMD [ "python", "/opt/mnoc_snmpcollector/collector.py" ]
