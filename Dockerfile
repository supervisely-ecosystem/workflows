FROM supervisely/base-py-sdk:6.72.41

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN mkdir /scripts

COPY release_everything.py /scripts/
COPY release.py /scripts/

CMD [ "python", "/scripts/release_everything.py > /logs/prod.log" ]
