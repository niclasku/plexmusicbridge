FROM python:3-alpine

COPY plexmusicbridge/ plexmusicbridge/
RUN pip install plexmusicbridge/

CMD [ "plexmusicbridge" ]