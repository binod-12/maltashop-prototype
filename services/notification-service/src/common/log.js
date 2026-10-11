// Structured JSON logger. Every line carries the mandatory schema from report section 4.2:
// timestamp, level, service, correlationId, event, message (+ optional extra fields).
const SERVICE = process.env.SERVICE_NAME || 'unknown-service';

export function log(level, event, message, correlationId = null, extra = {}) {
  const line = {
    timestamp: new Date().toISOString(),
    level,
    service: SERVICE,
    correlationId,
    event,
    message,
    ...extra,
  };
  // stdout only (12-factor XI: logs are an event stream)
  console.log(JSON.stringify(line));
}

export const info = (event, msg, cid, extra) => log('info', event, msg, cid, extra);
export const warn = (event, msg, cid, extra) => log('warn', event, msg, cid, extra);
export const error = (event, msg, cid, extra) => log('error', event, msg, cid, extra);
