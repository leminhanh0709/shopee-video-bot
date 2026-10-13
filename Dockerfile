FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fontconfig libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /usr/share/fonts/truetype/bevietnam && cp fonts/*.ttf /usr/share/fonts/truetype/bevietnam/ && fc-cache -f
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "app.main"]
