FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

EXPOSE 5002

ENTRYPOINT ["python", "validador.py"]
