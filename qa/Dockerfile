FROM mcr.microsoft.com/playwright/python:v1.56.0-noble
WORKDIR /app
COPY api/requirements.txt api/requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements-test.txt playwright==1.56.0
COPY api/app ./app
COPY qa/browser_test.py ./browser_test.py
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "browser_test.py"]
