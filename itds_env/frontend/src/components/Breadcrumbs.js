import React from 'react';
import { useLocation, Link } from 'react-router-dom';

const Breadcrumbs = () => {
  const location = useLocation();
  const parts = location.pathname.split('/').filter(Boolean);

  return (
    <nav aria-label="Breadcrumb" className="itds-breadcrumbs" style={{padding:'8px 0 16px'}}>
      <ol style={{listStyle:'none',display:'flex',gap:8,margin:0,padding:0,flexWrap:'wrap'}}>
        <li><Link to="/">Home</Link></li>
        {parts.map((p, idx) => {
          const to = '/' + parts.slice(0, idx + 1).join('/');
          const name = decodeURIComponent(p.replace(/-/g, ' '));
          return (
            <li key={to} aria-current={idx === parts.length - 1 ? 'page' : undefined}>
              <span style={{color:'#6b7280'}} aria-hidden="true">/</span>&nbsp;
              {idx === parts.length - 1 ? <span>{name}</span> : <Link to={to}>{name}</Link>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};

export default Breadcrumbs;
