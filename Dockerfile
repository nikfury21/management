FROM python:3.10-slim

# set work directory
WORKDIR /app

# install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy project files
COPY . .

# Render will set $PORT automatically
CMD ["python", "mng2.py"]
