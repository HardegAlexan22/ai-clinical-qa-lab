const fs = require('fs');
const path = require('path');
const Ajv = require('ajv');

// Local test key the service accepts by default; matches .env.example.
const API_KEY = process.env.QA_LAB_API_KEY || 'local-dev-key';
const AUTH = { 'x-api-key': API_KEY };

const ROOT = path.resolve(__dirname, '..', '..');
const groundTruth = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'fixtures', 'study_001_ground_truth.json'), 'utf-8'),
);

const ajv = new Ajv({ allErrors: true });
const validateSummarize = ajv.compile(require('./schemas/summarize-response.schema.json'));

async function summarize(request, body = {}) {
  return request.post('/summarize', {
    headers: AUTH,
    data: { study_id: 'study_001', ...body },
  });
}

module.exports = { API_KEY, AUTH, groundTruth, validateSummarize, summarize };
