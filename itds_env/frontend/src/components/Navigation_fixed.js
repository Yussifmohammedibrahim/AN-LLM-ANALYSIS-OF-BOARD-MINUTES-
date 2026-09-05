import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Settings, LogOut, Menu, X, User, Key, FileText
} from 'lucide-react';
import DynamicIcon from './DynamicIcon';
import { useConfirm } from './ConfirmProvider';
const Navigation = ({ user, showUploadModal, setShowUploadModal, refreshUser }) => {
  const { logout, isAdmin } = useAuth();
  const confirm = useConfirm();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

  useEffect(() => {
    if (!userMenuOpen) return undefined;

    const handleOutsideClick = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [userMenuOpen]);

  const handleLogout = async () => {
    try {
      const result = await confirm({
        title: 'Logout',
        message: 'Are you sure you want to logout?',
        actions: [{ label: 'Logout', value: 'logout', variant: 'danger' }],
        cancelLabel: 'Cancel'
      });
      if (result && result.action === 'logout') {
        await logout();
        navigate('/login');
      }
    } catch (err) {
      // ignore
    }
  };

  const navItems = [
    {path: '/', label: 'Dashboard', iconName: 'LayoutDashboard' },
    { path: '/charts', label: 'Charts', iconName: 'BarChart2' },
    { path: '/search', label: 'Search', iconName: 'Search' },
    { path: '/reports', label: 'Reports', iconName: 'FileText' },
    { path: '/upload', label: 'Upload', iconName: 'UploadCloud', roles: ['admin', 'editor'] },
    { path: '/users', label: 'Users', iconName: 'Users2', roles: ['admin'] },
    { path: '/activity', label: 'Recent Activity Logins', iconName: 'Clock', roles: ['admin'] }
  ];

  const filteredNavItems = navItems.filter(item => {
    if (!item.roles) return true;
    return item.roles.includes(user?.role);
  });

  const isActive = (path) => {
    if (path === '/') {
      return location.pathname === '/' || location.pathname === '/dashboard';
    }
    return location.pathname.startsWith(path);
  };

  return (
    <nav className="navbar">
      {/* Logo */}
      <Link to="/" className="navbar-brand">
        <img src="/ITDS.jpg" alt="ITDS Logo" className="nav-logo" />
        ITDS Board Minutes
      </Link>

      {/* Desktop Navigation */}
      <div className="navbar-menu hide-mobile">
        {filteredNavItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-link ${isActive(item.path) ? 'active' : ''}`}
          >
            <DynamicIcon name={item.iconName} size={18} />
            {item.label}
          
          </Link>
        ))}
      </div>

      {/* User Section */}
      <div className="user-section">
        {/* Settings Link */}
        <Link
          to="/settings"
          className={`nav-link hide-mobile ${isActive('/settings') ? 'active' : ''}`}
        >
          <Settings size={18} />
        </Link>

        {/* User Menu */}
        <div style={{ position: 'relative' }} ref={userMenuRef}>
          <div
            className="user-avatar"
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            style={{ cursor: 'pointer' }}
          >
            {user?.profile_image ? (
              <img 
src={`http://localhost:5000/uploads/profile_images/${user.profile_image}?t=${Date.now()}`}
                alt={user.username}
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  borderRadius: '50%'
                }}
                onError={(e) => {
                  e.target.style.display = 'none';
                  e.target.nextSibling.style.display = 'flex';
                }}
              />
            ) : null}
            <div 
              style={{
                width: '100%',
                height: '100%',
                background: 'var(--primary)',
                color: 'white',
                borderRadius: '50%',
                display: user?.profile_image ? 'none' : 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 'bold'
              }}
            >
              {user?.username?.charAt(0)?.toUpperCase()}
            </div>
          </div>

          {userMenuOpen && (
            <>
              <div
                style={{
                  position: 'fixed',
                  inset: 0,
                  zIndex: 9998
                }}
                onClick={() => setUserMenuOpen(false)}
              />
              <div
                style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: '0.5rem',
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  boxShadow: 'var(--shadow-lg)',
                  minWidth: '200px',
                  zIndex: 9999
                }}
              >
                <div style={{ padding: '1rem', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontWeight: 600 }}>{user?.username}</div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {user?.email || 'No email'}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', mt: '0.25rem' }}>
                    {user?.role}
                  </div>
                </div>
                <div style={{ padding: '0.5rem' }}>
                  <Link
                    to="/settings"
                    onClick={() => setUserMenuOpen(false)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.5rem 0.75rem',
                      borderRadius: 'var(--radius)',
                      fontSize: '0.875rem',
                      color: 'var(--text)',
                      transition: 'var(--transition-fast)'
                    }}
                    className="hover-bg"
                  >
                    <User size={16} />
                    Profile Settings
                  </Link>
                  <Link
                    to="/change-password"
                    onClick={() => setUserMenuOpen(false)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.5rem 0.75rem',
                      borderRadius: 'var(--radius)',
                      fontSize: '0.875rem',
                      color: 'var(--text)',
                      transition: 'var(--transition-fast)'
                    }}
                    className="hover-bg"
                  >
                    <Key size={16} />
                    Change Password
                  </Link>
                    <button
                      onClick={() => {
                        setUserMenuOpen(false);
                        setShowUploadModal(true);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        width: '100%',
                        padding: '0.5rem 0.75rem',
                        border: 'none',
                        background: 'transparent',
                        borderRadius: 'var(--radius)',
                        fontSize: '0.875rem',
                        color: 'var(--text)',
                        cursor: 'pointer',
                        transition: 'var(--transition-fast)',
                        textAlign: 'left'
                      }}
                      className="hover-bg profile-upload-item"
                    >
                      Upload Profile Image
                    </button>

                  <button
                    onClick={handleLogout}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      width: '100%',
                      padding: '0.5rem 0.75rem',
                      border: 'none',
                      background: 'transparent',
                      borderRadius: 'var(--radius)',
                      fontSize: '0.875rem',
                      color: 'var(--danger)',
                      cursor: 'pointer',
                      transition: 'var(--transition-fast)'
                    }}
                    className="hover-bg logout-item"
                  >
                    <LogOut size={16} />
                    Logout
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Mobile Menu Toggle */}
        <button
          className="btn btn-ghost btn-icon hide-desktop"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
{mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            zIndex: 99,
            display: 'flex',
            justifyContent: 'flex-end'
          }}
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            style={{
              width: '280px',
              background: 'var(--surface)',
              height: '100%',
              padding: '1rem',
              overflowY: 'auto'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ marginBottom: '1rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontWeight: '600' }}>{user?.username}</div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                {user?.email || 'No email'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {user?.role}
              </div>
            </div>
            
            {filteredNavItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setMobileMenuOpen(false)}
                className={`nav-link ${isActive(item.path) ? 'active' : ''}`}
                style={{ marginBottom: '0.25rem' }}
              >
                <DynamicIcon name={item.iconName} size={18} />
                {item.label}
              
              </Link>
            ))}
            
            <Link
              to="/settings"
              onClick={() => setMobileMenuOpen(false)}
              className={`nav-link ${isActive('/settings') ? 'active' : ''}`}
              style={{ marginBottom: '0.25rem' }}
            >
              <Settings size={18} />
              Settings
            </Link>
            
            <Link
              to="/change-password"
              onClick={() => setMobileMenuOpen(false)}
              className={`nav-link ${isActive('/change-password') ? 'active' : ''}`}
              style={{ marginBottom: '0.25rem' }}
            >
              <Key size={18} />
              Change Password
            </Link>
            
            <button
              onClick={handleLogout}
              className="nav-link"
              style={{
                width: '100%',
                marginTop: '1rem',
                color: 'var(--danger)',
                border: '1px solid var(--danger)'
              }}
            >
              <LogOut size={18} />
              Logout
            </button>
          </div>
        </div>
      )}

      <style>{`
        .hover-bg:hover {
          background: var(--surface-hover);
        }
        @media (min-width: 769px) {
          .hide-desktop {
            display: none !important;
          }
        }
        @media (max-width: 768px) {
          .hide-mobile {
            display: none !important;
          }
        }
      `}</style>
    </nav>
  );
};

export default Navigation;
