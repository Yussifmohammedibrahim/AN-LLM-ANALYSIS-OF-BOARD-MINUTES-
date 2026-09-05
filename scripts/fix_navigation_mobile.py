from pathlib import Path
import re

path = Path(r'c:\Users\DELL\Documents\itds_frameworks\itds_env\frontend\src\components\Navigation.js')
content = path.read_text(encoding='utf-8')

pattern = re.compile(r"\n      /\*\*? Mobile Menu \*/\n      \{mobileMenuOpen && \(\n.*?\n      \)\}\n\n      \{navLoading && \(", re.DOTALL)

replacement = """
      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div
          className=\"mobile-menu-overlay\"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            className=\"mobile-menu-panel\"
            onClick={(e) => e.stopPropagation()}
          >
            <div className=\"mobile-menu-header\">
              <div className=\"mobile-menu-name\">{user?.username}</div>
              <div className=\"mobile-menu-email\">
                {user?.email || t('navNoEmail')}
              </div>
              <div className=\"mobile-menu-role\">
                {user?.role}
              </div>
            </div>

            {filteredNavItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => handleNavClick(item.path, item.label, { closeMobile: true })}
                className={`nav-link mobile-menu-link ${isActive(item.path) ? 'active' : ''}`}
              >
                <DynamicIcon name={item.iconName} size={18} />
                {item.label}
              </Link>
            ))}

            <Link
              to=\"/notifications\"
              onClick={() => handleNavClick('/notifications', t('navNotifications'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/notifications') ? 'active' : ''}`}
            >
              <Bell size={18} />
              {t('navNotifications')}{notificationCount > 0 ? ` (${notificationCount})` : ''}
            </Link>

            <Link
              to=\"/settings\"
              onClick={() => handleNavClick('/settings', t('navSettings'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/settings') ? 'active' : ''}`}
            >
              <Settings size={18} />
              {t('navSettings')}
            </Link>

            {isAdmin() && (
              <Link
                to=\"/admin-tools\"
                onClick={() => handleNavClick('/admin-tools', t('navAdminTools'), { closeMobile: true })}
                className={`nav-link mobile-menu-link ${isActive('/admin-tools') ? 'active' : ''}`}
              >
                <Wrench size={18} />
                {t('navAdminTools')}
              </Link>
            )}

            <Link
              to=\"/change-password\"
              onClick={() => handleNavClick('/change-password', t('navChangePassword'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/change-password') ? 'active' : ''}`}
            >
              <Key size={18} />
              {t('navChangePassword')}
            </Link>

            <button
              onClick={handleLogout}
              className=\"nav-link mobile-menu-logout\"
            >
              <LogOut size={18} />
              {t('navLogout')}
            </button>
          </div>
        </div>
      )}

      {navLoading && ("""

new_content, count = pattern.subn(replacement, content, count=1)
if count != 1:
    raise SystemExit(f'Expected to replace 1 mobile menu block, replaced {count}')

path.write_text(new_content, encoding='utf-8')
print('Mobile menu block rewritten successfully')
