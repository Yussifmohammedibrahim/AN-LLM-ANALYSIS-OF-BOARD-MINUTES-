import React, { useState } from 'react';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import api, { aiAPI } from '../api/api';
import { useSelection } from './selection/SelectionContext';
import { notifyError, notifySuccess } from '../utils/notify';
import { useConfirm, usePrompt } from './ConfirmProvider';

const BulkActionsBar = ({ itemsMap = {}, activeTab = 'summaries', onDeleteComplete = null }) => {
  const { selected, clear } = useSelection();
  const confirm = useConfirm();
  const prompt = usePrompt();
  const [processing, setProcessing] = useState(false);

  const selectedIds = Array.from(selected);
  const selectedCount = selectedIds.length;

  const getSelectedRows = () => selectedIds.map((id) => itemsMap[id]).filter(Boolean);

  const getExportColumns = () => {
    if (activeTab === 'topics') {
      return [
        { header: 'Topic', key: 'name' },
        { header: 'Occurrences', key: 'topic_occurrences' },
        { header: 'Confidence', key: 'confidence' },
      ];
    }
    if (activeTab === 'keywords') {
      return [
        { header: 'Keywords', key: 'keywords' },
        { header: 'Confidence', key: 'confidence' },
      ];
    }
    if (activeTab === 'sentiment') {
      return [
        { header: 'Sentiment', key: 'sentiment' },
        { header: 'Confidence', key: 'confidence' },
      ];
    }
    if (activeTab === 'actions') {
      return [
        { header: 'Action Item', key: 'item_text' },
        { header: 'Status', key: 'status' },
        { header: 'Confidence', key: 'confidence' },
      ];
    }
    return [
      { header: 'Summary', key: 'summary_text' },
      { header: 'Confidence', key: 'confidence' },
    ];
  };

  const handleExportPDF = () => {
    if (!selectedCount) return;
    const rows = getSelectedRows();
    const columns = getExportColumns();
    const doc = new jsPDF({ orientation: activeTab === 'topics' ? 'landscape' : 'portrait' });

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(14);
    doc.text(`${activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} Export`, 14, 14);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.text(`Selected items: ${selectedCount}`, 14, 20);

    const body = rows.map((row, index) => columns.map((column) => {
      const value = row?.[column.key];
      if (value === null || typeof value === 'undefined' || value === '') return index + 1 && column.key === columns[0].key ? `Row ${index + 1}` : '-';
      if (Array.isArray(value)) return value.join(', ');
      return String(value).replace(/\s+/g, ' ').trim();
    }));

    autoTable(doc, {
      startY: 26,
      head: [columns.map((column) => column.header)],
      body,
      styles: { fontSize: 8, cellPadding: 2, overflow: 'linebreak', valign: 'top' },
      headStyles: { fillColor: [37, 99, 235] },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      margin: { left: 14, right: 14 },
    });

    doc.save(`export_${activeTab}_${Date.now()}.pdf`);
    notifySuccess(`${selectedCount} items exported as PDF`);
  };

  const handleDelete = async () => {
    if (!selectedCount) return;
    const result = await confirm({
      title: 'Delete Selected Items',
      message: `Delete ${selectedCount} selected items? This is permanent.`,
      actions: [{ label: 'Delete', value: 'delete', variant: 'danger' }],
      cancelLabel: 'Cancel',
    });
    if (result.action !== 'delete') return;
    setProcessing(true);
    try {
      await Promise.all(selectedIds.map(id => aiAPI.deleteReportItem(id)));
      notifySuccess(`${selectedCount} items deleted`);
      clear();
      if (typeof onDeleteComplete === 'function') {
        await onDeleteComplete();
      } else {
        window.location.reload();
      }
    } catch (err) {
      notifyError('Failed to delete selected items');
    } finally {
      setProcessing(false);
    }
  };

  const handleEmail = async () => {
    if (!selectedCount) return;
    const toResult = await prompt({
      title: 'Email Selected Items',
      message: 'Send selected items to email (comma-separated allowed):',
      inputLabel: 'Recipient email(s)',
      placeholder: 'name@example.com, team@example.com',
      submitLabel: 'Continue',
      cancelLabel: 'Cancel',
      validate: (value) => (value ? true : 'Recipient email is required.'),
    });
    if (toResult.action !== 'submit') return;

    const subjectResult = await prompt({
      title: 'Email Subject',
      message: 'Set a subject for this email.',
      inputLabel: 'Subject',
      defaultValue: `Selected ${activeTab} from ITDS`,
      submitLabel: 'Send',
      cancelLabel: 'Cancel',
      trim: false,
    });
    if (subjectResult.action !== 'submit') return;

    const to = toResult.value;
    const subject = subjectResult.value;
    setProcessing(true);
    try {
      const rows = getSelectedRows();
      const resp = await api.post('/api/notifications/send-bulk-email', {
        recipient_email: to,
        subject,
        report_type: activeTab,
        rows,
      });
      if (resp.status >= 400) throw new Error(resp.data?.error || 'Email API failed');
      notifySuccess('Email queued/sent');
      clear();
    } catch (err) {
      notifyError(err.message || 'Failed to send email');
    } finally {
      setProcessing(false);
    }
  };

  if (!selectedCount) return null;

  return (
    <div className="bulk-actions-bar" role="region" aria-label="Bulk actions" style={{display:'flex',gap:8,alignItems:'center',marginBottom:12}}>
      <div><strong>{selectedCount}</strong> selected</div>
      <div style={{display:'flex',gap:8}}>
        <button className="btn btn-outline" onClick={handleExportPDF} disabled={processing}>Export PDF</button>
        <button className="btn btn-secondary" onClick={handleEmail} disabled={processing}>Email Selected</button>
        <button className="btn btn-danger" onClick={handleDelete} disabled={processing}>Delete Selected</button>
      </div>
    </div>
  );
};

export default BulkActionsBar;
