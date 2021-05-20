FROM python:3

COPY plexmusicbridge/ plexmusicbridge/
RUN pip install plexmusicbridge/

CMD [ "plexmusicbridge" ]