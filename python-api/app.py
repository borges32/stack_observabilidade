from flask import Flask, jsonify, abort
import mysql.connector
import os
import time
import random

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter


from opentelemetry.instrumentation.flask import FlaskInstrumentor

# --- OpenTelemetry setup ---
resource = Resource.create({SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "python-api")})


# Tracing setup
trace_provider = TracerProvider(resource=resource)

trace_exporter = OTLPSpanExporter(endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"), insecure=True)
span_processor = BatchSpanProcessor(trace_exporter)
trace_provider.add_span_processor(span_processor)
trace.set_tracer_provider(trace_provider)

# Metrics setup

metric_exporter = OTLPMetricExporter(endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"), insecure=True)
metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10000)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)

# Create meter and counter
meter = metrics.get_meter(__name__)
counter = meter.create_counter(
    "pedidos_count", description="Número de pedidos"
)

# Flask app
app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
tracer = trace.get_tracer(__name__)

# DB configuration
DB_CONF = {
    'host': os.getenv("DB_HOST", 'mysql'),
    'user': os.getenv("DB_USER", 'app'),
    'password': os.getenv("DB_PASS", 'apppass'),
    'database': os.getenv("DB_NAME", 'pedidos_db')
}

# Wait for MySQL to be ready
max_retries = 10
for attempt in range(1, max_retries + 1):
    try:
        conn = mysql.connector.connect(**DB_CONF)
        conn.close()
        print(f"Connected to MySQL on attempt {attempt}")
        break
    except mysql.connector.Error as err:
        print(f"MySQL connection attempt {attempt} failed: {err}")
        time.sleep(5)
else:
    print(f"Could not connect to MySQL after {max_retries} attempts, exiting.")
    exit(1)

# Initialize database (create table if not exists)
conn = mysql.connector.connect(**DB_CONF)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS pedidos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  status VARCHAR(20),
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()
cursor.close()
conn.close()


def maybe_fail():
    """Gera um valor entre 0 e 20 e força erro 500 se for 5 ou 7."""
    v = random.randint(0, 20)
    print(f"[InjectFault] valor={v}")
    if v in (5, 7):
        abort(500, description=f"Erro injetado (valor={v})")

@app.route('/novo_pedido', methods=['POST'])
def novo_pedido():

    maybe_fail()  # Inject a fault randomly

    with tracer.start_as_current_span("novo_pedido"):
        conn = mysql.connector.connect(**DB_CONF)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pedidos (status) VALUES ('aberto')")
        conn.commit()
        cursor.close()
        conn.close()
        counter.add(1, {"status": "aberto"})
        return jsonify({"status": "ok", "pedido": "aberto"})

@app.route('/fechar_pedido', methods=['POST'])
def fechar_pedido():
    maybe_fail()

    with tracer.start_as_current_span("fechar_pedido"):
        conn = mysql.connector.connect(**DB_CONF)
        cursor = conn.cursor()
        cursor.execute("UPDATE pedidos SET status='fechado' WHERE status='aberto'")
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        counter.add(affected, {"status": "fechado"})
        return jsonify({"status": "ok", "pedidos_fechados": affected})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)