FROM python:3.12-slim
RUN pip install --no-cache-dir tzdata \
 && useradd --create-home app
WORKDIR /app
COPY --chown=app:app . /app
USER app
EXPOSE 8765
VOLUME /app/private
CMD ["python", "-X", "utf8", "server.py", "--lan"]