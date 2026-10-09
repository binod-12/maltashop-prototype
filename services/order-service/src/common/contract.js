// Minimal JSON-schema-style validator (type, required, properties, items, minimum, minLength).
// Dependency-free on purpose; enough for consumer-driven contract checks between two services.
export function validate(schema, value, path = '$') {
  const errors = [];
  const t = schema.type;
  const actual = Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value;

  if (t) {
    const ok = t === 'integer' ? Number.isInteger(value) : t === actual;
    if (!ok) return [`${path}: expected ${t}, got ${actual}`];
  }
  if (schema.minimum !== undefined && value < schema.minimum) errors.push(`${path}: below minimum ${schema.minimum}`);
  if (schema.minLength !== undefined && String(value).length < schema.minLength) errors.push(`${path}: shorter than ${schema.minLength}`);
  if (t === 'object') {
    for (const key of schema.required || []) {
      if (!(key in value)) errors.push(`${path}.${key}: required field missing`);
    }
    for (const [key, sub] of Object.entries(schema.properties || {})) {
      if (key in value) errors.push(...validate(sub, value[key], `${path}.${key}`));
    }
  }
  if (t === 'array' && schema.items) {
    value.forEach((v, i) => errors.push(...validate(schema.items, v, `${path}[${i}]`)));
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(`${path}: needs at least ${schema.minItems} item(s)`);
  }
  return errors;
}
