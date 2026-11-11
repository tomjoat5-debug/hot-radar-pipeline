FROM python:3.12-slim

WORKDIR /app

COPY radar_pipeline ./radar_pipeline

# One run: fetch -> clean -> store -> report.
# The report and database live in /app/reports and /app/data;
# mount them to keep the output, e.g.:
#   docker run --rm -v "$PWD/reports:/app/reports" -v "$PWD/data:/app/data" hot-radar
CMD ["python", "-m", "radar_pipeline.run"]
