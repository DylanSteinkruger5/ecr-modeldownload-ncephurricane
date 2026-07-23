FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Native libs for pygrib/pyproj/shapely + matplotlib fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libeccodes0 libeccodes-dev libopenjp2-7 \
    proj-bin proj-data libproj-dev \
    libgeos-dev \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip && pip install \
    numpy==2.2.4 pygrib cloudflare==2.19.4 matplotlib zstandard metpy \
    boto3==1.35.14 geojsoncontour mapbox-earcut pyresample shapely \
    contourpy==1.3.2 pyproj==3.7.1 scipy pandas requests

COPY lambda_function.py ./
COPY PressureCenterFinderTerrain.py ./
COPY ModelHelpers.py ./

ENTRYPOINT ["python"]
