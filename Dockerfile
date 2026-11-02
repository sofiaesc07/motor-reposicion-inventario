FROM apache/airflow:3.0.6-python3.11
COPY --chown=airflow:0 requirements.txt /tmp/inventory-requirements.txt
RUN pip install --no-cache-dir -r /tmp/inventory-requirements.txt
ENV PYTHONPATH=/opt/inventory/src
