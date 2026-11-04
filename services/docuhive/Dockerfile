FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS build
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY LICENSE ./
COPY services/docuhive/ services/docuhive/
COPY evals/ evals/
COPY config/defaults/ config/defaults/
RUN pip install --no-cache-dir uv==0.11.13 \
    && uv build --package docuhive --out-dir /wheels \
    && uv export --frozen --package docuhive --all-extras --no-dev --no-emit-workspace \
       --format requirements-txt > /requirements.txt

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS runtime
# OCRmyPDF 16.13; Tesseract 5.x from Bookworm. Record actual versions with each benchmark.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng ghostscript unpaper \
    pngquant qpdf libheif1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home docuhive
COPY --from=build /requirements.txt /requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /requirements.txt \
    && rm /requirements.txt
COPY --from=build /wheels/ /wheels/
RUN pip install --no-cache-dir --no-deps /wheels/*.whl && rm -rf /wheels
WORKDIR /app
USER 1000:1000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["docuhive"]
CMD ["api", "--host", "0.0.0.0"]
