FROM python:3.7

WORKDIR /home/cdb

COPY requirements.txt requirements.txt
RUN pip install -r ./requirements.txt
RUN pip install gunicorn
RUN pip install psycopg2

COPY runprodguni.sh ./
RUN chmod +x runprodguni.sh

COPY setup.py ./setup.py
COPY app app
COPY migrations migrations
COPY config.prod.cfg ./config.prod.cfg

EXPOSE 5123
ENTRYPOINT ["./runprodguni.sh"]