FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV MPLCONFIGDIR=/tmp/matplotlib
CMD ["python", "scripts/demo.py"]
