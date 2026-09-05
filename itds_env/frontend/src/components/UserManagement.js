import React, { useState, useEffect, useCallback } from 'react';
import { adminAPI } from '../api/api';
import { ensureArray } from '../utils/safeMap';
import { useAuth } from '../context/AuthContext';
import { notifyError, notifySuccess } from '../utils/notify';
import { useLanguage } from '../context/LanguageContext';
import { useConfirm, usePrompt } from './ConfirmProvider';


const UserManagement = () => {
  const { t } = useLanguage();

  const { isAdmin, isSuperAdmin } = useAuth();
  const confirm = useConfirm();
  const prompt = usePrompt();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [createConflict, setCreateConflict] = useState(null);
  const [showDeleted, setShowDeleted] = useState(false);
  const [newUser, setNewUser] = useState({
    username: '',
    email: '',
    full_name: '',
    contact_number: '',
    role: 'viewer'
  });
  const [creating, setCreating] = useState(false);

  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      const response = await adminAPI.getUsers({ include_deleted: showDeleted ? 1 : 0 });
      setUsers(ensureArray(response.data || response.data.users));
    } catch (error) {
      if (error.response?.status === 403) {
        notifyError(t('umAdminRequired'));
      } else {
        notifyError(t('umLoadUsersFailed'));
      }
    } finally {
      setLoading(false);
    }
  }, [showDeleted, t]);

  useEffect(() => {
    if (!isAdmin()) {
      notifyError(t('umAdminRequired'));
      return;
    }
    loadUsers();
  }, [isAdmin, loadUsers, t]);

  const handleAddUser = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const response = await adminAPI.createUser(newUser);
      notifySuccess(t('umUserCreated', { username: newUser.username }));

      console.log('Temp password:', response.data.temp_password);
      
      setShowAddModal(false);
      setCreateConflict(null);
      setNewUser({ username: '', email: '', full_name: '', contact_number: '', role: 'viewer' });
      await loadUsers();
    } catch (error) {
      const deletedUserConflict = error.response?.status === 409 && error.response?.data?.conflict_type === 'deleted_user_exists'
        ? {
            userId: error.response?.data?.deleted_user_id,
            username: error.response?.data?.deleted_username,
            email: error.response?.data?.deleted_email,
          }
        : null;

      if (deletedUserConflict) {
        setCreateConflict(deletedUserConflict);
      }

      const errorMsg = deletedUserConflict
        ? t('umDeletedUserConflict')
        : (error.response?.data?.error || t('umCreateFailed'));
      notifyError(errorMsg);
    } finally {
      setCreating(false);
    }
  };

  const handleRoleChange = async (userId, newRole) => {
    try {
      const targetUser = users.find((item) => item.user_id === userId);
      if (!targetUser || targetUser.role === newRole) {
        return;
      }
      if (targetUser?.role === 'super_admin' && !isSuperAdmin()) {
        notifyError(t('umOnlySuperAdminModify'));
        return;
      }
      if (newRole === 'super_admin' && !isSuperAdmin()) {
        notifyError(t('umOnlySuperAdminAssign'));
        return;
      }
      await adminAPI.updateUser(userId, { role: newRole });
      notifySuccess(t('umRoleUpdated'));
      await loadUsers();
    } catch (error) {
      notifyError(t('umRoleUpdateFailed'));
    }
  };

  const [editingUser, setEditingUser] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [updating, setUpdating] = useState(false);

  const handleEditUser = (user) => {
    if (user?.role === 'super_admin' && !isSuperAdmin()) {
      notifyError(t('umOnlySuperAdminModify'));
      return;
    }
    setEditingUser({ ...user });
    setShowEditModal(true);
  };

  const handleUpdateUser = async (e) => {
    e.preventDefault();
    if (editingUser?.role === 'super_admin' && !isSuperAdmin()) {
      notifyError(t('umOnlySuperAdminModify'));
      return;
    }
    setUpdating(true);
    try {
      await adminAPI.updateUser(editingUser.user_id, editingUser);
      notifySuccess(t('umDetailsUpdated'));
      setShowEditModal(false);
      setEditingUser(null);
      await loadUsers();
    } catch (error) {
      notifyError(error.response?.data?.error || t('umDetailsUpdateFailed'));
    } finally {
      setUpdating(false);
    }
  };

  const handleDeleteUser = async (userId) => {
    const targetUser = users.find((item) => item.user_id === userId);
    if (targetUser?.role === 'super_admin' && !isSuperAdmin()) {
      notifyError(t('umOnlySuperAdminModify'));
      return;
    }

    const promptResult = await prompt({
      title: t('delete'),
      message: t('umDeleteReasonPrompt'),
      inputLabel: t('umDeleteReasonPrompt'),
      placeholder: t('umDeleteReasonPrompt'),
      submitLabel: t('submit'),
      cancelLabel: t('cancel'),
      validate: (value) => (value ? true : t('umDeleteReasonPrompt')),
    });
    if (promptResult.action !== 'submit') return;
    const reason = promptResult.value;
    try {
      await adminAPI.deleteUser(userId, { reason });
      notifySuccess(t('umMovedToTrash'));
      await loadUsers();
    } catch (error) {
      notifyError(error.response?.data?.error || t('umDeleteFailed'));
    }
  };

  const handleRestoreUser = async (userId) => {
    try {
      await adminAPI.restoreUser(userId);
      notifySuccess(t('umRestored'));
      await loadUsers();
    } catch (error) {
      notifyError(error.response?.data?.error || t('umRestoreFailed'));
    }
  };

  const handleRestoreConflictUser = async (userId) => {
    try {
      await adminAPI.restoreUser(userId);
      notifySuccess(t('umDeletedRestored'));
      setCreateConflict(null);
      await loadUsers();
    } catch (error) {
      notifyError(error.response?.data?.error || t('umRestoreFailed'));
    }
  };

  const handlePurgeUser = async (userId) => {
    if (!isSuperAdmin()) {
      notifyError(t('umOnlySuperAdminPurge'));
      return;
    }
    const result = await confirm({
      title: t('umPurge'),
      message: t('umPurgeConfirm'),
      actions: [{ label: t('umPurge'), value: 'purge', variant: 'danger' }],
      cancelLabel: t('cancel'),
    });
    if (result.action !== 'purge') return;
    try {
      await adminAPI.purgeUser(userId);
      notifySuccess(t('umPurged'));
      await loadUsers();
    } catch (error) {
      notifyError(error.response?.data?.error || t('umPurgeFailed'));
    }
  };

  if (loading) {
    return <div className="loading min-h-screen"><div className="spinner"></div></div>;
  }
 
  return (
    <div className="page-content">
      <div className="dashboard">
        <div className="dashboard-header">
          <h1>{t('umTitle')}</h1>
          <p>{t('umSubtitle')}</p>
        </div>

        {isSuperAdmin() && (
          <div className="mb-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
              {t('umShowDeleted')}
            </label>
          </div>
        )}

        <div className="mb-4">
          <button className="btn btn-primary" onClick={() => {
            setCreateConflict(null);
            setShowAddModal(true);
          }} disabled={creating}>
            {t('umAddNewUser')}
          </button>
        </div>

        <div className="card">
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('umColUsername')}</th>
                  <th>{t('umColEmail')}</th>
                  <th>{t('umColName')}</th>
                  <th>{t('umColContact')}</th>
                  <th>{t('umColRole')}</th>
                  <th>{t('umColCreated')}</th>
                  <th>{t('umColActions')}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.user_id}>
                    <td><span className="font-semibold">{user.username}</span></td>
                    <td>{user.email || t('reportsNA')}</td>
                    <td>{user.full_name || t('reportsNA')}</td>
                    <td>{user.contact_number || t('reportsNA')}</td>
                    <td>
                      <select 
                        className="form-select form-select-sm"
                        value={user.role}
                        onChange={(e) => handleRoleChange(user.user_id, e.target.value)}
                        disabled={user.role === 'super_admin' && !isSuperAdmin()}
                      >
                        <option value="viewer">{t('umRoleViewer')}</option>
                        <option value="editor">{t('umRoleEditor')}</option>
                        <option value="admin">{t('umRoleAdmin')}</option>
                        {isSuperAdmin() && <option value="super_admin">{t('umRoleSuperAdmin')}</option>}
                      </select>
                      {Boolean(user.is_deleted) && <div className="mt-1 text-xs text-warning">{t('umDeletedBadge')}</div>}
                    </td>
                    <td>{user.created_at ? new Date(user.created_at).toLocaleString('en-US', { year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : t('reportsNA')}</td>
<td>
                      <div className="button-group">
                        <button className="btn btn-outline btn-sm" onClick={() => handleEditUser(user)}>
                          {t('edit')}
                        </button>
                        {user.is_deleted ? (
                          <>
                            <button className="btn btn-success btn-sm" onClick={() => handleRestoreUser(user.user_id)}>
                              {t('umRestore')}
                            </button>
                            {isSuperAdmin() && (
                              <button className="btn btn-danger btn-sm" onClick={() => handlePurgeUser(user.user_id)}>
                                {t('umPurge')}
                              </button>
                            )}
                          </>
                        ) : (
                          <button className="btn btn-danger btn-sm" onClick={() => handleDeleteUser(user.user_id)}>
                            {t('delete')}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan="7" className="text-center py-8 text-muted">
                      {t('umNoUsers')} <button className="btn btn-primary btn-sm" onClick={() => setShowAddModal(true)}>{t('umCreateFirst')}</button>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Add Modal */}
{showAddModal && (
  <div className="modal-overlay" onClick={(e) => {
    if (e.target === e.currentTarget) {
      setShowAddModal(false);
      setCreateConflict(null);
    }
  }}>
    <div className="modal" onClick={(e) => e.stopPropagation()}>
      <div className="modal-header">
        <h3>{t('umAddNewUserTitle')}</h3>
        <button className="modal-close" onClick={() => {
          setShowAddModal(false);
          setCreateConflict(null);
        }}>×</button>
      </div>
      <form onSubmit={handleAddUser}>
        <div className="modal-body">
          <div className="form-row">
            <div className="form-group">
              <label>{t('umUsernameLabel')}</label>
              <input type="text" className="form-input" value={newUser.username} onChange={(e) => setNewUser({...newUser, username: e.target.value})} required />
            </div>
            <div className="form-group">
              <label>{t('umRoleLabel')}</label>
              <select className="form-select" value={newUser.role} onChange={(e) => setNewUser({...newUser, role: e.target.value})}>
                <option value="viewer">{t('umRoleViewer')}</option>
                <option value="editor">{t('umRoleEditor')}</option>
                <option value="admin">{t('umRoleAdmin')}</option>
                {isSuperAdmin() && <option value="super_admin">{t('umRoleSuperAdmin')}</option>}
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>{t('umEmailLabel')}</label>
              <input type="email" className="form-input" value={newUser.email} onChange={(e) => setNewUser({...newUser, email: e.target.value})} required />
            </div>
            <div className="form-group">
              <label>{t('umFullNameLabel')}</label>
              <input type="text" className="form-input" value={newUser.full_name} onChange={(e) => setNewUser({...newUser, full_name: e.target.value})} />
            </div>
          </div>
          <div className="form-group">
            <label>{t('umContactLabel')}</label>
            <input type="tel" className="form-input" value={newUser.contact_number} onChange={(e) => setNewUser({...newUser, contact_number: e.target.value})} />
          </div>
          <div className="alert alert-info">
            {t('umTempPasswordInfo')}
            {isSuperAdmin() && ` ${t('umSuperAdminCreateInfo')}`}
          </div>
          {createConflict && (
            <div className="alert alert-warning">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-semibold">{t('umConflictTitle')}</div>
                  <div className="text-sm">
                    {createConflict.username}
                    {createConflict.email ? ` (${createConflict.email})` : ''}
                    . {t('umConflictBody')}
                  </div>
                </div>
                {isSuperAdmin() && createConflict.userId && (
                  <button
                    type="button"
                    className="btn btn-success btn-sm"
                    onClick={() => handleRestoreConflictUser(createConflict.userId)}
                    disabled={creating}
                  >
                    {t('umRestoreDeletedUser')}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-outline" onClick={() => {
            setShowAddModal(false);
            setCreateConflict(null);
          }} disabled={creating}>{t('cancel')}</button>
          <button type="submit" className="btn btn-primary" disabled={creating}>
            {creating ? t('umCreating') : t('umCreateUser')}
          </button>
        </div>
      </form>
    </div>
  </div>
)}

        {/* Edit Modal */}
{showEditModal && editingUser && (
  <div className="modal-overlay" onClick={(e) => {
    if (e.target === e.currentTarget) setShowEditModal(false);
  }}>
    <div className="modal" onClick={(e) => e.stopPropagation()}>
      <div className="modal-header">
        <h3>{t('umEditUser', { username: editingUser.username })}</h3>
        <button className="modal-close" onClick={() => setShowEditModal(false)}>×</button>
      </div>
      <form onSubmit={handleUpdateUser}>
        <div className="modal-body">
          <div className="form-row">
            <div className="form-group">
              <label>{t('umColUsername')}</label>
              <input type="text" className="form-input" value={editingUser.username} disabled />
            </div>
            <div className="form-group">
              <label>{t('umColRole')}</label>
              <select className="form-select" value={editingUser.role} onChange={(e) => setEditingUser({...editingUser, role: e.target.value})} disabled={updating}>
                <option value="viewer">{t('umRoleViewer')}</option>
                <option value="editor">{t('umRoleEditor')}</option>
                <option value="admin">{t('umRoleAdmin')}</option>
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>{t('umColEmail')}</label>
              <input type="email" className="form-input" value={editingUser.email || ''} onChange={(e) => setEditingUser({...editingUser, email: e.target.value})} disabled={updating} />
            </div>
            <div className="form-group">
              <label>{t('umFullNameLabel')}</label>
              <input type="text" className="form-input" value={editingUser.full_name || ''} onChange={(e) => setEditingUser({...editingUser, full_name: e.target.value})} disabled={updating} />
            </div>
          </div>
          <div className="form-group">
            <label>{t('umContactLabel')}</label>
            <input type="tel" className="form-input" value={editingUser.contact_number || ''} onChange={(e) => setEditingUser({...editingUser, contact_number: e.target.value})} disabled={updating} />
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-outline" onClick={() => setShowEditModal(false)} disabled={updating}>{t('cancel')}</button>
          <button type="submit" className="btn btn-primary" disabled={updating}>
            {updating ? t('umUpdating') : t('umUpdateUser')}
          </button>
        </div>
      </form>
    </div>
  </div>
)}
      </div>
    </div>
  );
};

export default UserManagement;

