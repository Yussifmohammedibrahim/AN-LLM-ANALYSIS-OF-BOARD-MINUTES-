import React, { createContext, useContext, useMemo, useState } from 'react';

const SelectionContext = createContext(null);

export const SelectionProvider = ({ children }) => {
  const [selected, setSelected] = useState(new Set());

  const toggle = (id) => {
    setSelected((prev) => {
      const copy = new Set(prev);
      if (copy.has(id)) copy.delete(id);
      else copy.add(id);
      return copy;
    });
  };

  const selectAll = (ids = []) => {
    setSelected(new Set(ids));
  };

  const clear = () => setSelected(new Set());

  const remove = (id) => {
    setSelected((prev) => {
      const copy = new Set(prev);
      copy.delete(id);
      return copy;
    });
  };

  const value = useMemo(() => ({ selected, toggle, selectAll, clear, remove }), [selected]);

  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
};

export const useSelection = () => {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error('useSelection must be used within SelectionProvider');
  return ctx;
};

export default SelectionContext;
