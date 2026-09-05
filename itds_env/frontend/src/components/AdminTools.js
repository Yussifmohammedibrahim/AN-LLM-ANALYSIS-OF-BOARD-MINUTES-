import React, { useState } from 'react';
import { ShieldAlert, Trash2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useQueryClient } from '@tanstack/react-query';
import api from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import { useConfirm, usePrompt } from './ConfirmProvider';

const AdminTools = () => {
  const { isAdmin, isSuperAdmin } = useAuth();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const prompt = usePrompt();
  const [clearing, setClearing] = useState(false);

  if (!isAdmin()) {
    return (
      <div className="page-content">
        <div className="dashboard">
          <div className="card">
            <div className="card-body">
              <p>Admin access is required.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const clearAllMinutes = async () => {
    const promptResult = await prompt({
      title: 'Confirm Cleanup Phrase',
      message: 'Type DELETE ALL MINUTES to clear every minute and recording.',
      inputLabel: 'Confirmation phrase',
      placeholder: 'DELETE ALL MINUTES',
      submitLabel: 'Continue',
      cancelLabel: 'Cancel',
      validate: (value) => (value === 'DELETE ALL MINUTES' ? true : 'Phrase does not match.'),
    });
    if (promptResult.action !== 'submit') return;

    const result = await confirm({
      title: 'Clear All Minutes',
      message: 'This will move all minutes to trash and clear their analysis. Continue?',
      actions: [{ label: 'Continue', value: 'continue', variant: 'danger' }],
      cancelLabel: 'Cancel',
    });
    if (result.action !== 'continue') return;

    setClearing(true);
    try {
      await api.delete('/api/ai/transcripts?full_cleanup=1');

      // Clear cached dashboard/report data so UI reflects deletion immediately.
      queryClient.setQueryData(['dashboard-stats'], {
        totalMeetings: 0,
        totalSegments: 0,
        actionItems: 0,
        themes: 0,
      });
      queryClient.setQueryData(['dashboard-charts'], {
        themeData: { labels: [], datasets: [] },
        sentimentData: { labels: [], datasets: [] },
        trendsData: { labels: [], datasets: [] },
      });
      queryClient.setQueryData(['dashboard-insights'], []);
      queryClient.setQueryData(['dashboard-activity'], []);
      queryClient.setQueryData(['dashboard-realtime'], {
        stats: { totalRecordings: 0, avgSentimentScore: 0, mostFrequentKeyword: null, analyzedCount: 0 },
        liveFeed: [],
        charts: null,
      });
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-charts'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-insights'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-activity'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-realtime'] });

      notifySuccess('All minutes, summaries, and analysis records were cleared.');
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to clear all minutes.');
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="page-content">
      <div className="dashboard">
        <div className="dashboard-header">
          <h1 className="dashboard-title">Admin Tools</h1>
          <p className="dashboard-subtitle">System cleanup and maintenance actions</p>
        </div>

        <div className="settings-container">
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">
                <ShieldAlert size={20} style={{ marginRight: '0.5rem' }} />
                Minute Cleanup
              </h3>
            </div>
            <div className="card-body">
              <p className="text-sm text-secondary mb-4">
                Clear every minute and recording from the application. This is admin-only and should be used carefully.
              </p>
              <button className="btn btn-danger" onClick={clearAllMinutes} disabled={clearing}>
                <Trash2 size={16} />
                {clearing ? 'Clearing...' : 'Clear All Minutes'}
              </button>
              {isSuperAdmin() && (
                <p className="text-xs text-secondary mt-3">
                  Super admin accounts can still recover data from trash if needed.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminTools;