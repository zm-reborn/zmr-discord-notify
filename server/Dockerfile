FROM python:3.11

COPY requirements.txt zmrdiscordnotify.py /app/
WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

CMD python ./zmrdiscordnotify.py
