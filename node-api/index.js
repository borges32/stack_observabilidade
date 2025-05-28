const express = require('express');
const axios = require('axios');
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');

const sdk = new NodeSDK({
  serviceName: process.env.OTEL_SERVICE_NAME || 'node-api',
  traceExporter: {
    endpoint: process.env.OTEL_EXPORTER_OTLP_ENDPOINT
  },
  metricExporter: {
    endpoint: process.env.OTEL_EXPORTER_OTLP_ENDPOINT
  },
  instrumentations: [getNodeAutoInstrumentations()],
});
sdk.start();

const app = express();
app.use(express.json());

app.post('/trigger', async (req, res) => {
  try {
    await axios.post(`${process.env.PYTHON_API}/novo_pedido`);
    await axios.post(`${process.env.PYTHON_API}/fechar_pedido`);
    res.json({ status: 'done' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(4000, () => {
  console.log('Node API listening on port 4000');
});
