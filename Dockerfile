FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY prompts ./prompts
# EXTRAS=[semantic] adds fastembed for the semantic cache (larger image)
ARG EXTRAS=""
RUN pip install --no-cache-dir ".${EXTRAS}"
EXPOSE 8000
CMD ["uvicorn", "serving.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
