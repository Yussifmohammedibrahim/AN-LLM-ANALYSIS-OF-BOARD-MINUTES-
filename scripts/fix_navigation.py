import re

filepath = 'itds_env/frontend/src/components/Navigation.js'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the mobile nav items map - add missing className and children
old_mobile_map = r'''            {filteredNavItems\.map\(\(item\) => \(
              <Link
                key={item\.path}
                to={item\.path}
                 onClick=\{\(\) => handleNavClick\(item\.path, item\.label, \{ closeMobile: true \}\)\}
              </Link>
            \)\)}'''

new_mobile_map = '''            {filteredNavItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => handleNavClick(item.path, item.label, { closeMobile: true })}
                className={`nav-link mobile-menu-link ${isActive(item.path) ? 'active' : ''}`}
              >
                <DynamicIcon name={item.iconName} size={18} />
                {item.label}
              </Link>
            ))}'''

content = re.sub(old_mobile_map, new_mobile_map, content)

# Fix the settings link
old_settings = r'''            <Link
              to="/settings"
               onClick=\{\(\) => handleNavClick\('/settings', t\('navSettings'\), \{ closeMobile: true \}\)\}
              <Settings size=\{18\} />
              \{t\('navSettings'\)\}
            </Link>'''

new_settings = '''            <Link
              to="/settings"
              onClick={() => handleNavClick('/settings', t('navSettings'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/settings') ? 'active' : ''}`}
            >
              <Settings size={18} />
              {t('navSettings')}
            </Link>'''

content = re.sub(old_settings, new_settings, content)

# Fix change-password link
old_changepw = r'''            <Link
              to="/change-password"
               onClick=\{\(\) => handleNavClick\('/change-password', t\('navChangePassword'\), \{ closeMobile: true \}\)\}
              <Key size=\{18\} />
              \{t\('navChangePassword'\)\}
            </Link>'''

new_changepw = '''            <Link
              to="/change-password"
              onClick={() => handleNavClick('/change-password', t('navChangePassword'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/change-password') ? 'active' : ''}`}
            >
              <Key size={18} />
              {t('navChangePassword')}
            </Link>'''

content = re.sub(old_changepw, new_changepw, content)

# Fix /notifications link (missing closing paren)
old_notif = r'''             onClick=\{\(\) => handleNavClick\('/notifications', t\('navNotifications'\), \{ closeMobile: true \}\)'''
new_notif = '''              onClick={() => handleNavClick('/notifications', t('navNotifications'), { closeMobile: true })}'''
content = content.replace(old_notif, new_notif)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Navigation.js fixed successfully")
