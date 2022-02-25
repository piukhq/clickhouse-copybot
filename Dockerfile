FROM ghcr.io/binkhq/python:3.10 as build

WORKDIR /app
COPY . .

RUN pipenv install --system --deploy --ignore-pipfile
