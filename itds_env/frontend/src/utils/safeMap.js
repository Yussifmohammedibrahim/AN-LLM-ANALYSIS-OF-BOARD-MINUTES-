export const ensureArray = (value) => {
  if (Array.isArray(value)) return value;
  if (value === null || value === undefined) return [];
  return [value];
};

export const safeMap = (array, fn) => {
  return (array || []).map(fn).filter(Boolean);
};

