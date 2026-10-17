function parse(output) {
  try {
    return JSON.parse(output);
  } catch (error) {
    return { parse_error: String(error), tool_sequence: [] };
  }
}

function hasTools(required) {
  return (output) => {
    const result = parse(output);
    const actual = result.tool_sequence || [];
    const pass = required.every((name) => actual.includes(name));
    return {
      pass,
      score: pass ? 1 : 0,
      reason: `herramientas observadas: ${actual.join(', ')}`,
    };
  };
}

function orderedTools(required) {
  return (output) => {
    const result = parse(output);
    const actual = result.tool_sequence || [];
    let cursor = -1;
    const pass = required.every((name) => {
      cursor = actual.indexOf(name, cursor + 1);
      return cursor >= 0;
    });
    return {
      pass,
      score: pass ? 1 : 0,
      reason: `secuencia observada: ${actual.join(' -> ')}`,
    };
  };
}

function forbidsTools(forbidden) {
  return (output) => {
    const result = parse(output);
    const actual = result.tool_sequence || [];
    const pass = forbidden.every((name) => !actual.includes(name));
    return {
      pass,
      score: pass ? 1 : 0,
      reason: `herramientas observadas: ${actual.join(', ')}`,
    };
  };
}

function fieldEquals(field, expected) {
  return (output) => {
    const result = parse(output);
    const actual = field.split('.').reduce((value, key) => value?.[key], result);
    const pass = actual === expected;
    return { pass, score: pass ? 1 : 0, reason: `${field}=${actual}` };
  };
}

module.exports = { hasTools, orderedTools, forbidsTools, fieldEquals };
