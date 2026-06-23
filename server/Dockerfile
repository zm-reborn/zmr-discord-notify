FROM python:3.14

COPY requirements.txt client.py webapp.py run.py /app/
WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

CMD python ./run.py
