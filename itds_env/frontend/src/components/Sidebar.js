import React from 'react';
import { NavLink } from 'react-router-dom';
import './Sidebar.css';

const Sidebar = () => {
  return (
    <nav className="itds-sidebar" aria-label="Primary navigation">
      <ul>
        <li><NavLink to="/" end>Dashboard</NavLink></li>
        <li><NavLink to="/trend-analysis">Trends</NavLink></li>
        <li><NavLink to="/reports">Reports</NavLink></li>
        <li><NavLink to="/search">Search</NavLink></li>
        <li><NavLink to="/users">Users</NavLink></li>
        <li><NavLink to="/settings">Settings</NavLink></li>
      </ul>
    </nav>
  );
};

export default Sidebar;
